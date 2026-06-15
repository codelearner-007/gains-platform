#!/usr/bin/env bash
# 07-pause-azure.sh — REVERSIBLE pause/stop of the legacy Azure footprint.
#
# Stops everything that drives cost EXCEPT the Blob storage account (the new
# platform reads pre_landing/Schoology/ from it). Every action here is
# reversible with 08-resume-azure.sh — there are NO deletes, NO --force, and the
# storage account is never touched.
#
# What it does:
#   1. az aks stop        — stops all .NET microservices + MSSQL + RabbitMQ +
#                           Redis (data stays on their persistent disks)
#   2. PBI capacity suspend — Power BI Embedded A1 -> billing $0
#   3. Synapse triggers stop — no pipeline runs (Spark pools then stay idle = $0)
#
# KEEPS RUNNING (untouched): storage stoeaprodtest2 (Blob), ACR, Key Vault,
# Synapse workspace baseline, Log Analytics — all near-zero when idle and needed
# for a clean restore.
#
# Usage:
#   ./07-pause-azure.sh            # DRY RUN — prints what it would do, changes nothing
#   ./07-pause-azure.sh --apply    # actually pause
set -uo pipefail

HERE="$(cd "$(dirname "$0")" && pwd)"
[[ -f "$HERE/.env" ]] && source "$HERE/.env"

RG="${LEGACY_RG:-EdvancelsResourceGroupEastus2}"
AKS="${LEGACY_AKS:-EdvancelsAKSClusterEastus2}"
DATA_RG="${LEGACY_DATA_RG:-rg-oea-prodtest2}"
SYNAPSE="${LEGACY_SYNAPSE:-syn-oea-prodtest2}"
PBI_CAPACITY="${LEGACY_PBI_CAPACITY:-powerbicapacity1}"
KEEP_STORAGE="${LEGACY_STORAGE_ACCT:-stoeaprodtest2}"   # NEVER touched

APPLY=0
[[ "${1:-}" == "--apply" ]] && APPLY=1

run() {  # run <description> <cmd...>
  local desc="$1"; shift
  if [[ $APPLY -eq 1 ]]; then
    echo "▶ $desc"
    if "$@"; then echo "  ✓ done"; else echo "  ✗ FAILED (continuing): $*"; fi
  else
    echo "[dry-run] would: $desc"
    echo "          cmd: $*"
  fi
}

echo "=================================================================="
echo " PAUSE legacy Azure  (mode: $([[ $APPLY -eq 1 ]] && echo APPLY || echo DRY-RUN))"
echo " App RG:  $RG   AKS: $AKS   PBI: $PBI_CAPACITY"
echo " Data RG: $DATA_RG   Synapse: $SYNAPSE"
echo " KEEPING (never touched): storage '$KEEP_STORAGE', ACR, Key Vault"
echo "=================================================================="

# 1) AKS — the biggest cost (3 nodes + all pods). Stop is fully reversible.
echo; echo "── 1. AKS cluster ─────────────────────────────────────────────"
PWR=$(az aks show -g "$RG" -n "$AKS" --query powerState.code -o tsv 2>/dev/null || echo "?")
echo "current power state: $PWR"
if [[ "$PWR" == "Running" ]]; then
  run "stop AKS $AKS (preserves MSSQL/RabbitMQ/Redis on disk)" \
      az aks stop -g "$RG" -n "$AKS"
else
  echo "  (already not Running — skip)"
fi

# 2) Power BI Embedded capacity — suspend (resume to undo).
echo; echo "── 2. Power BI Embedded capacity ──────────────────────────────"
run "suspend PBI capacity $PBI_CAPACITY" \
    az resource invoke-action --action suspend \
      --resource-group "$RG" --name "$PBI_CAPACITY" \
      --resource-type "Microsoft.PowerBIDedicated/capacities"

# 3) Synapse triggers — stop all so no pipeline launches Spark/copy jobs.
echo; echo "── 3. Synapse triggers ────────────────────────────────────────"
TRIGGERS=$(az synapse trigger list --workspace-name "$SYNAPSE" \
             --query "[].name" -o tsv 2>/dev/null)
if [[ -z "$TRIGGERS" ]]; then
  echo "  (no triggers found — Spark pools auto-pause when idle = \$0)"
else
  while IFS= read -r t; do
    [[ -z "$t" ]] && continue
    run "stop trigger '$t'" \
        az synapse trigger stop --workspace-name "$SYNAPSE" --name "$t"
  done <<< "$TRIGGERS"
fi

echo; echo "=================================================================="
echo " Spark pools (spark3p3sm, sparkPool34) bill only while a job runs; with"
echo " triggers stopped they stay idle at \$0. Serverless SQL = pay-per-query."
echo
echo " NOT paused (intentionally kept, near-zero idle cost, needed to restore):"
echo "   • storage '$KEEP_STORAGE'  (Blob — new platform reads pre_landing/)"
echo "   • ACR, Key Vault, Synapse workspace baseline, Log Analytics"
echo
echo " Outside Azure CLI (stop manually if still running):"
echo "   • Power Automate Desktop ingestion / Schoology scraper"
echo
echo " To UNDO everything:  ./08-resume-azure.sh --apply"
[[ $APPLY -eq 0 ]] && echo; [[ $APPLY -eq 0 ]] && echo " (DRY RUN — nothing changed. Re-run with --apply to pause.)"
echo "=================================================================="
