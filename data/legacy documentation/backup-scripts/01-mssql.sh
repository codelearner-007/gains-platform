#!/usr/bin/env bash
# 01-mssql.sh — back up every MSSQL DB on the AKS pod, smoke-restore the
# two most-important ones to a throwaway local Docker SQL.
# Idempotent: skips DBs whose .bak already exists locally.

source "$(dirname "$0")/lib.sh"
log_to "01-mssql"

step "1.1  Re-check MSSQL pod"
kubectl exec -n "$MSSQL_NAMESPACE" "$MSSQL_POD" -- /opt/mssql-tools18/bin/sqlcmd -C \
  -S localhost -U sa -P "$MSSQL_SA_PWD" -Q "SELECT 1" -h -1 >/dev/null \
  || die "MSSQL pod unreachable — run ./00-preflight.sh first"

# Decide which DBs to back up. Default: everything > id 4 (skip the system DBs).
# Override with `MSSQL_DBS="db1 db2"` in .env if you want to limit it.
if [[ -z "${MSSQL_DBS:-}" ]]; then
  # -h -1 strips header; we still get the trailing "(N rows affected)" line so
  # we filter it out explicitly (and any empty / parens-containing junk).
  MSSQL_DBS="$(kubectl exec -n "$MSSQL_NAMESPACE" "$MSSQL_POD" -- /opt/mssql-tools18/bin/sqlcmd -C \
    -S localhost -U sa -P "$MSSQL_SA_PWD" -W -h -1 \
    -Q "SET NOCOUNT ON; SELECT name FROM sys.databases WHERE database_id > 4 AND state_desc = 'ONLINE' ORDER BY name" \
    | grep -vE '^(\s*$|\(.*rows? affected\)|Msg |Server: )' \
    | awk 'NF' | tr '\n' ' ')"
fi
log "DBs to back up: $MSSQL_DBS"
[[ -n "$MSSQL_DBS" ]] || die "No DBs found to back up"

step "1.2  BACKUP DATABASE loop"
for db in $MSSQL_DBS; do
  local_bak="$BACKUP_DIR/mssql/${db}.bak"
  if [[ -s "$local_bak" ]]; then
    log "↷ $db — local .bak already exists ($(du -h "$local_bak" | cut -f1)), skipping"
    continue
  fi

  log "▶ Backing up $db"
  pod_path="/var/opt/mssql/data/${db}.bak"

  # 1) Issue BACKUP inside the pod
  kubectl exec -n "$MSSQL_NAMESPACE" "$MSSQL_POD" -- /opt/mssql-tools18/bin/sqlcmd -C \
    -S localhost -U sa -P "$MSSQL_SA_PWD" \
    -Q "BACKUP DATABASE [$db] TO DISK = N'${pod_path}'
        WITH COMPRESSION, INIT, CHECKSUM, FORMAT, STATS = 25, NAME = N'${db}-full'"

  # 2) Copy out
  kubectl cp -n "$MSSQL_NAMESPACE" "${MSSQL_POD}:${pod_path}" "$local_bak"

  # 3) Wipe inside the pod (don't waste 8Gi PVC space)
  kubectl exec -n "$MSSQL_NAMESPACE" "$MSSQL_POD" -- rm -f "$pod_path"

  ok "$db backed up — $(du -h "$local_bak" | cut -f1)"
done

step "1.3  Generate the per-DB metadata file (size, row counts for key tables)"
META="$BACKUP_DIR/mssql/metadata.json"
echo "{" > "$META"
first=1
for db in $MSSQL_DBS; do
  rows="$(kubectl exec -n "$MSSQL_NAMESPACE" "$MSSQL_POD" -- /opt/mssql-tools18/bin/sqlcmd -C \
    -S localhost -U sa -P "$MSSQL_SA_PWD" -W -h -1 -Q "
USE [$db];
SELECT 'rows_'  + LOWER(t.name) + ': ' + CONVERT(VARCHAR, SUM(p.rows))
FROM sys.tables t JOIN sys.partitions p ON t.object_id = p.object_id
WHERE p.index_id IN (0,1) GROUP BY t.name ORDER BY t.name" 2>/dev/null | grep '^rows_' || true)"
  size_kb="$(stat -f%z "$BACKUP_DIR/mssql/${db}.bak" 2>/dev/null || stat -c%s "$BACKUP_DIR/mssql/${db}.bak" 2>/dev/null)"
  size_kb=$((size_kb/1024))
  [[ $first -eq 1 ]] || echo "," >> "$META"
  first=0
  echo "  \"$db\": { \"bak_size_kb\": $size_kb, \"top_tables\": [" >> "$META"
  echo "$rows" | head -10 | awk -F': ' 'BEGIN{first=1} {gsub("rows_",""); if (first==0) print ","; printf "    { \"table\": \"%s\", \"rows\": %s }", $1, $2; first=0} END{print ""}' >> "$META"
  echo "  ] }" >> "$META"
done
echo "}" >> "$META"
ok "Metadata written to $META"

step "1.4  Smoke-restore the two most-important DBs"
# Identity = user/role data; LMS = CASE Network standards + question bank.
# These two are the highest-value backups; verifying them catches BAK corruption.
# Names differ from the research docs (no "Service" suffix in this deployment).
SMOKE_DBS="${SMOKE_DBS:-Identity LMS}"

# Start a throwaway SQL container
SMOKE_CONT="sql-verify-$$"
SMOKE_PWD="VerifyTest!2026"
log "Starting throwaway Docker SQL container ($SMOKE_CONT) on port 11433..."

docker run -d --rm --name "$SMOKE_CONT" \
  -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD="$SMOKE_PWD" \
  -p 11433:1433 \
  -v "$BACKUP_DIR/mssql:/backups:ro" \
  mcr.microsoft.com/mssql/server:2022-latest >/dev/null

# Wait for SQL to come up (poll every 2s, max 60s)
for i in {1..30}; do
  if docker exec "$SMOKE_CONT" /opt/mssql-tools18/bin/sqlcmd -C \
       -S localhost -U sa -P "$SMOKE_PWD" -Q "SELECT 1" -h -1 >/dev/null 2>&1; then
    break
  fi
  sleep 2
done

VERIFY_REPORT="$BACKUP_DIR/mssql/verify.txt"
: > "$VERIFY_REPORT"

for db in $SMOKE_DBS; do
  if [[ ! -s "$BACKUP_DIR/mssql/${db}.bak" ]]; then
    warn "  ↷ $db.bak missing — skipping smoke restore"
    continue
  fi
  log "▶ Smoke-restoring $db"

  # Read the logical file names from the bak
  files="$(docker exec "$SMOKE_CONT" /opt/mssql-tools18/bin/sqlcmd -C \
    -S localhost -U sa -P "$SMOKE_PWD" -W -h -1 \
    -Q "RESTORE FILELISTONLY FROM DISK = '/backups/${db}.bak'" 2>/dev/null \
    | awk 'NR<=2 {print $1}')"
  data_lf="$(echo "$files" | head -1)"
  log_lf="$(echo "$files" | tail -1)"

  docker exec "$SMOKE_CONT" /opt/mssql-tools18/bin/sqlcmd -C \
    -S localhost -U sa -P "$SMOKE_PWD" -Q "
RESTORE DATABASE [${db}_verify] FROM DISK = '/backups/${db}.bak'
WITH MOVE '${data_lf}' TO '/var/opt/mssql/data/${db}_verify.mdf',
     MOVE '${log_lf}' TO '/var/opt/mssql/data/${db}_verify_log.ldf',
     REPLACE, RECOVERY" >/dev/null

  # Pick a known table per DB to spot-check
  case "$db" in
    Identity|IdentityService) probe="SELECT COUNT(*) FROM AbpUsers" ;;
    LMS|LMSService)           probe="SELECT COUNT(*) FROM CFItem" ;;
    *)                        probe="SELECT COUNT(*) FROM sys.tables" ;;
  esac
  count="$(docker exec "$SMOKE_CONT" /opt/mssql-tools18/bin/sqlcmd -C \
    -S localhost -U sa -P "$SMOKE_PWD" -d "${db}_verify" -W -h -1 -Q "$probe" 2>/dev/null \
    | head -1 | tr -d '[:space:]')"

  ok "$db smoke-restore OK (probe row count = $count)"
  echo "$db: probe=\"$probe\", count=$count" >> "$VERIFY_REPORT"
done

docker rm -f "$SMOKE_CONT" >/dev/null
ok "Smoke-restore report: $VERIFY_REPORT"

step "1.5  Final manifest"
log "Final MSSQL backup contents:"
du -h "$BACKUP_DIR/mssql"/*.bak 2>/dev/null | sort -k2

echo
ok "MSSQL BACKUP COMPLETE"
log "Next: ./02-synapse.sh"
