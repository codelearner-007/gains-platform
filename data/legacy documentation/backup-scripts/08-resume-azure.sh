#!/usr/bin/env bash
# 08-resume-azure.sh — UNDO 07-pause-azure.sh. Brings the legacy footprint back.
#
# Restarts AKS, resumes the Power BI capacity, and re-enables Synapse triggers.
# Mirror of the pause script; no data was lost (pause never deleted anything).
#
# Usage:
#   ./08-resume-azure.sh           # DRY RUN
#   ./08-resume-azure.sh --apply   # actually resume
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
[[ -f "$HERE/.env" ]] && source "$HERE/.env"

RG="${LEGACY_RG:-EdvancelsResourceGroupEastus2}"
AKS="${LEGACY_AKS:-EdvancelsAKSClusterEastus2}"
SYNAPSE="${LEGACY_SYNAPSE:-syn-oea-prodtest2}"
PBI_CAPACITY="${LEGACY_PBI_CAPACITY:-powerbicapacity1}"

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

run() {
  local desc="$1"; shift
  if [[ $APPLY -eq 1 ]]; then
    echo "▶ $desc"
    if "$@"; then echo "  ✓ done"; else echo "  ✗ FAILED (continuing): $*"; fi
  else
    echo "[dry-run] would: $desc"; echo "          cmd: $*"
  fi
}

echo "=================================================================="
echo " RESUME legacy Azure  (mode: $([[ $APPLY -eq 1 ]] && echo APPLY || echo DRY-RUN))"
echo "=================================================================="

echo; echo "── 1. Start AKS ───────────────────────────────────────────────"
run "start AKS $AKS" az aks start -g "$RG" -n "$AKS"

echo; echo "── 2. Resume Power BI capacity ────────────────────────────────"
run "resume PBI capacity $PBI_CAPACITY" \
    az resource invoke-action --action resume \
      --resource-group "$RG" --name "$PBI_CAPACITY" \
      --resource-type "Microsoft.PowerBIDedicated/capacities"

echo; echo "── 3. Start Synapse triggers ──────────────────────────────────"
TRIGGERS=$(az synapse trigger list --workspace-name "$SYNAPSE" \
             --query "[].name" -o tsv 2>/dev/null)
if [[ -z "$TRIGGERS" ]]; then
  echo "  (no triggers to start)"
else
  while IFS= read -r t; do
    [[ -z "$t" ]] && continue
    run "start trigger '$t'" \
        az synapse trigger start --workspace-name "$SYNAPSE" --name "$t"
  done <<< "$TRIGGERS"
fi

echo; echo "=================================================================="
echo " Resume issued. AKS start takes a few minutes to pull nodes + pods up."
echo " Verify:  az aks show -g $RG -n $AKS --query powerState.code -o tsv"
[[ $APPLY -eq 0 ]] && echo " (DRY RUN — nothing changed.)"
echo "=================================================================="
