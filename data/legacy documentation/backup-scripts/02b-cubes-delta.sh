#!/usr/bin/env bash
# 02b-cubes-delta.sh — Delta-aware cube backup.
#
# For each of the 8 canonical cubes, reads the cube's _delta_log to identify
# only the live (non-tombstoned) parquet files, then downloads ONLY those
# via azcopy. Result is a clean snapshot of what the legacy reports actually
# render — without years of tombstoned Delta versions.

source "$(dirname "$0")/lib.sh"
log_to "02b-cubes-delta"

step "2b.1  Generate read-only SAS"
if date -u -v+24H +%s >/dev/null 2>&1; then
  EXPIRY="$(date -u -v+24H +%Y-%m-%dT%H:%MZ)"
else
  EXPIRY="$(date -u -d '+24 hours' +%Y-%m-%dT%H:%MZ)"
fi
SAS="$(az storage account generate-sas \
  --account-name "$LEGACY_STORAGE_ACCT" \
  --services bfqt --resource-types sco \
  --permissions rl \
  --expiry "$EXPIRY" \
  --https-only -o tsv)"
[[ -n "$SAS" ]] || die "Failed to generate SAS"
ok "SAS valid until $EXPIRY"

step "2b.2  Install deltalake into throwaway venv"
PY="$(command -v python3 || command -v python)"
[[ -n "$PY" ]] || die "Need python3"

VENV="$BACKUP_DIR/.delta-venv"
if [[ ! -x "$VENV/bin/python" ]]; then
  "$PY" -m venv "$VENV"
fi
"$VENV/bin/pip" install --quiet --upgrade pip
"$VENV/bin/pip" install --quiet 'deltalake>=0.18' pyarrow
PY="$VENV/bin/python"
ok "deltalake installed"

CUBES=(
  Cube_Grade_Summary
  Cube_School_Summary
  Cube_Standard_Summary
  Cube_Question_Summary
  Cube_Question_Summary_Overall
  Cube_QuestionIncorrectChoice_Summary
  Cube_User_Summary
  Cube_OverallPerformance_Summary
)

CUBES_DIR="$BACKUP_DIR/synapse/stage3_cubes"
mkdir -p "$CUBES_DIR"

# Account-level base URL (deltalake uses az:// scheme, azcopy uses https://)
DELTA_BASE="az://oea/dev/stage3/Published/schoology/v0.1"
HTTP_BASE="https://${LEGACY_STORAGE_ACCT}.dfs.core.windows.net/oea/dev/stage3/Published/schoology/v0.1"

# Pass storage credentials to the Python script via env (more reliable than
# CLI args because SAS contains '&', '=', etc.)
export AZURE_STORAGE_ACCOUNT_NAME="$LEGACY_STORAGE_ACCT"
export AZURE_STORAGE_SAS_TOKEN="$SAS"

step "2b.3  For each cube — enumerate live files via _delta_log"
LIST_DIR="$BACKUP_DIR/synapse/.cube-live-lists"
mkdir -p "$LIST_DIR"

for cube in "${CUBES[@]}"; do
  out="$LIST_DIR/${cube}.txt"
  log "▶ Enumerating live files for $cube"
  "$PY" - "$cube" "$out" <<'PYEOF'
import os, sys
from deltalake import DeltaTable

cube, out_path = sys.argv[1], sys.argv[2]
url = f"az://oea/dev/stage3/Published/schoology/v0.1/{cube}"
storage_options = {
    "account_name": os.environ["AZURE_STORAGE_ACCOUNT_NAME"],
    "sas_token":    os.environ["AZURE_STORAGE_SAS_TOKEN"],
}

dt = DeltaTable(url, storage_options=storage_options)
uris = dt.file_uris()                               # abs URIs of live files
prefix = url.rstrip("/") + "/"
rels = []
for u in uris:
    if u.startswith(prefix):
        rels.append(u[len(prefix):])
    else:
        # az:// vs azure:// scheme drift — fall back to last-N segments after cube name
        idx = u.find(f"/{cube}/")
        rels.append(u[idx + len(cube) + 2:] if idx >= 0 else u)
with open(out_path, "w") as f:
    for rel in rels:
        f.write(rel + "\n")
print(f"{cube}: {len(rels)} live files")
PYEOF
done

step "2b.4  Download each cube's live parquet via azcopy --list-of-files"
TOTAL_FILES=0
TOTAL_MB_EST=0
for cube in "${CUBES[@]}"; do
  list="$LIST_DIR/${cube}.txt"
  local_path="$CUBES_DIR/$cube"

  count="$(wc -l < "$list" | tr -d ' ')"
  log "▶ $cube — $count live parquet files"
  TOTAL_FILES=$((TOTAL_FILES + count))

  if [[ -d "$local_path" ]] && find "$local_path" -name '*.parquet' -print -quit 2>/dev/null | grep -q .; then
    log "↷ $cube already populated, skipping"
    continue
  fi
  mkdir -p "$local_path"

  azcopy copy \
    "${HTTP_BASE}/${cube}?${SAS}" \
    "$local_path/" \
    --recursive \
    --list-of-files "$list" \
    --log-level=INFO \
    --output-type=text 2>&1 \
    | tee -a "$LOG_DIR/azcopy-cube-${cube}.log" \
    | grep -E "Final Job|Number of File Transfers Completed|Total Number of Bytes Transferred" || true

  size_mb=$(du -sm "$local_path" | cut -f1)
  ok "$cube → ${size_mb} MB local"
done

step "2b.5  Verify a parquet from each cube reads"
VERIFY="$BACKUP_DIR/synapse/verify-cubes.txt"
: > "$VERIFY"
for cube in "${CUBES[@]}"; do
  sample="$(find "$CUBES_DIR/$cube" -name '*.parquet' 2>/dev/null | head -1)"
  if [[ -z "$sample" ]]; then
    echo "$cube: NO PARQUET" >> "$VERIFY"
    warn "$cube: no parquet"
    continue
  fi
  out="$("$PY" -c "
import pyarrow.parquet as pq
t = pq.read_table('$sample')
print(f'{t.num_rows} rows, {t.num_columns} cols')
")"
  echo "$cube → $(basename "$sample"): $out" >> "$VERIFY"
  ok "$cube → $out"
done

step "2b.6  Stage1 canonical Delta — same trick"
S1_DIR="$BACKUP_DIR/synapse/stage1_transactional"
mkdir -p "$S1_DIR"

STAGE1=(question_data roles standards student_submissions submission_summary users)
HTTP_S1_BASE="https://${LEGACY_STORAGE_ACCT}.dfs.core.windows.net/oea/dev/stage1/Transactional/schoology/v0.1"

for tbl in "${STAGE1[@]}"; do
  out="$LIST_DIR/stage1-${tbl}.txt"
  log "▶ stage1/$tbl — enumerating"
  "$PY" - "$tbl" "$out" <<'PYEOF'
import os, sys
from deltalake import DeltaTable
tbl, out_path = sys.argv[1], sys.argv[2]
url = f"az://oea/dev/stage1/Transactional/schoology/v0.1/{tbl}"
storage_options = {
    "account_name": os.environ["AZURE_STORAGE_ACCOUNT_NAME"],
    "sas_token":    os.environ["AZURE_STORAGE_SAS_TOKEN"],
}
try:
    dt = DeltaTable(url, storage_options=storage_options)
    uris = dt.file_uris()
    prefix = url.rstrip("/") + "/"
    rels = []
    for u in uris:
        if u.startswith(prefix):
            rels.append(u[len(prefix):])
        else:
            idx = u.find(f"/{tbl}/")
            rels.append(u[idx + len(tbl) + 2:] if idx >= 0 else u)
    with open(out_path, "w") as f:
        for rel in rels: f.write(rel + "\n")
    print(f"{tbl}: {len(rels)} live files")
except Exception as e:
    print(f"{tbl}: SKIP — {e}", file=sys.stderr)
    open(out_path, "w").close()  # empty list
PYEOF
  count="$(wc -l < "$out" | tr -d ' ')"
  if [[ "$count" == "0" ]]; then
    warn "stage1/$tbl: no live files (or not a Delta table)"
    continue
  fi
  local_path="$S1_DIR/$tbl"
  if [[ -d "$local_path" ]] && find "$local_path" -name '*.parquet' -print -quit 2>/dev/null | grep -q .; then
    log "↷ stage1/$tbl already populated, skipping"
    continue
  fi
  mkdir -p "$local_path"
  azcopy copy \
    "${HTTP_S1_BASE}/${tbl}?${SAS}" \
    "$local_path/" \
    --recursive \
    --list-of-files "$out" \
    --log-level=INFO \
    --output-type=text 2>&1 \
    | tee -a "$LOG_DIR/azcopy-stage1-${tbl}.log" \
    | grep -E "Final Job|Number of File Transfers Completed" || true
  size_mb=$(du -sm "$local_path" | cut -f1)
  ok "stage1/$tbl → ${size_mb} MB"
done

step "2b.7  Final summary"
log "Per-area sizes:"
du -sh "$BACKUP_DIR/synapse/pre_landing" 2>/dev/null
du -sh "$BACKUP_DIR/synapse/stage1_transactional" 2>/dev/null
du -sh "$BACKUP_DIR/synapse/stage3_cubes" 2>/dev/null
echo
log "Total:"
du -sh "$BACKUP_DIR/synapse"

# Clean up the .cube-live-lists folder
rm -rf "$LIST_DIR"

echo
ok "DELTA-AWARE CUBE BACKUP COMPLETE"
log "Next: ./03-keyvault.sh"
