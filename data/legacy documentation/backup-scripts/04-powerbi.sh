#!/usr/bin/env bash
# 04-powerbi.sh — download every report (.pbix or .rdl) from all 5 Power BI
# workspaces via the Power BI REST API. No manual clicking in app.powerbi.com.

source "$(dirname "$0")/lib.sh"
log_to "04-powerbi"

step "4.1  Acquire Power BI access token"
TOKEN="$(az account get-access-token --resource https://analysis.windows.net/powerbi/api --query accessToken -o tsv 2>&1)"
[[ -n "$TOKEN" ]] || die "Failed to get Power BI access token"
ok "Token acquired"

PBI_API="https://api.powerbi.com/v1.0/myorg"
PBI_DIR="$BACKUP_DIR/powerbi"
mkdir -p "$PBI_DIR"

# Workspace name → ID
declare -a WORKSPACES=(
  "ReportWithCube:8215049c-ebd6-4a9b-bb98-5b5fdb7d3da4"
  "Athenian-Prod:4a060743-d330-4f5d-bdeb-09a6f9199610"
  "South-Prep:659cbf81-123b-4d63-b642-eea821c16d81"
  "CrestWell-School:b1703f33-da5d-4495-b2c2-bb9548c14e64"
  "Central-Florida:817a0155-cff7-4dd3-9772-ceeea3bd5217"
)

step "4.2  Export each report from each workspace"
TOTAL=0
FAILED=0
SUMMARY="$BACKUP_DIR/powerbi/summary.txt"
: > "$SUMMARY"

for ws_entry in "${WORKSPACES[@]}"; do
  ws_name="${ws_entry%%:*}"
  ws_id="${ws_entry##*:}"
  ws_dir="$PBI_DIR/$ws_name"
  mkdir -p "$ws_dir"
  log "▶ Workspace: $ws_name ($ws_id)"

  # List reports in this workspace
  reports_json="$(curl -s -H "Authorization: Bearer $TOKEN" "$PBI_API/groups/$ws_id/reports")"
  count=$(echo "$reports_json" | jq '.value | length' 2>/dev/null)
  log "  $count reports to export"

  # Iterate
  echo "$reports_json" | jq -r '.value[] | "\(.id)\t\(.name)\t\(.reportType // "PowerBIReport")"' | \
  while IFS=$'\t' read -r rid rname rtype; do
    # Skip auto-generated usage metrics reports
    case "$rname" in
      "Usage Metrics Report"|"Report Usage Metrics Report"|"Report Usage Metrics Model")
        log "  ↷ skip: $rname (auto-generated usage)"
        continue
        ;;
    esac

    # Choose extension based on report type
    case "$rtype" in
      PaginatedReport) ext="rdl" ;;
      *)               ext="pbix" ;;
    esac

    # Sanitize filename
    safe_name="$(echo "$rname" | tr '/' '-' | tr -d '"')"
    out_file="$ws_dir/${safe_name}.${ext}"
    if [[ -s "$out_file" ]]; then
      log "  ↷ $rname.$ext already exists (skip)"
      continue
    fi

    log "  ▶ exporting $rname [$rtype]"
    http_code=$(curl -s -o "$out_file" -w "%{http_code}" \
      -H "Authorization: Bearer $TOKEN" \
      "$PBI_API/groups/$ws_id/reports/$rid/Export")

    if [[ "$http_code" == "200" ]]; then
      sz=$(du -h "$out_file" | cut -f1)
      ok "  $rname.$ext → $sz"
      echo "$ws_name/$rname.$ext: $sz [$rtype]" >> "$SUMMARY"
      TOTAL=$((TOTAL + 1))
    else
      err_body="$(cat "$out_file" 2>/dev/null | head -c 300)"
      warn "  ✗ HTTP $http_code — $err_body"
      rm -f "$out_file"
      echo "$ws_name/$rname.$ext: FAILED (HTTP $http_code)" >> "$SUMMARY"
      FAILED=$((FAILED + 1))
    fi
  done
done

step "4.3  Summary"
log "Per-workspace contents:"
for ws_entry in "${WORKSPACES[@]}"; do
  ws_name="${ws_entry%%:*}"
  if [[ -d "$PBI_DIR/$ws_name" ]]; then
    log "  $ws_name:"
    ls -lh "$PBI_DIR/$ws_name"/*.{pbix,rdl} 2>/dev/null | awk '{print "    " $9 ": " $5}' | sed "s|$PBI_DIR/$ws_name/||g"
  fi
done

log "Total exported: $TOTAL files / Failed: $FAILED"
log "Disk used:"
du -sh "$PBI_DIR"

echo
ok "POWER BI BACKUP COMPLETE"
cat "$SUMMARY"
