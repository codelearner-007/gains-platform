#!/usr/bin/env bash
# 00-preflight.sh — verify everything is ready to back up.
# Idempotent. Run as many times as you want.

source "$(dirname "$0")/lib.sh"
log_to "00-preflight"

step "0.1  Verify required tools"
require_tool az      "brew install azure-cli"
require_tool kubectl "brew install kubectl"
require_tool azcopy  "brew install azcopy"
require_tool age     "brew install age"
require_tool jq      "brew install jq"
require_tool docker  "Docker Desktop, or: brew install --cask docker"
ok "All required CLIs present"

step "0.2  Verify .env values"
for v in LEGACY_SUB_ID LEGACY_RG LEGACY_AKS LEGACY_DATA_RG LEGACY_SYNAPSE \
         LEGACY_STORAGE_ACCT LEGACY_KV_OEA \
         MSSQL_NAMESPACE MSSQL_POD MSSQL_SA_PWD; do
  require_env "$v"
done
# LEGACY_KV_LMS is optional (only Insight Analytics tenant — single KV)
: "${LEGACY_KV_LMS:=}"
print_state
ok ".env values look ok"

step "0.3  Verify Azure login + subscription"
if ! az account show >/dev/null 2>&1; then
  log "Not logged in — running 'az login'"
  az login --only-show-errors >/dev/null
fi
az account set --subscription "$LEGACY_SUB_ID"
ACTIVE_SUB="$(az account show --query id -o tsv)"
[[ "$ACTIVE_SUB" == "$LEGACY_SUB_ID" ]] || die "Failed to set subscription"
ok "Azure subscription set: $ACTIVE_SUB"

step "0.4  Verify resource group + resources exist"
az group show -n "$LEGACY_RG" --query name -o tsv >/dev/null \
  || die "Resource group $LEGACY_RG not found"
az group show -n "$LEGACY_DATA_RG" --query name -o tsv >/dev/null \
  || die "Data resource group $LEGACY_DATA_RG not found"
az aks show -n "$LEGACY_AKS" -g "$LEGACY_RG" --query name -o tsv >/dev/null \
  || die "AKS cluster $LEGACY_AKS not found"
az synapse workspace show -n "$LEGACY_SYNAPSE" -g "$LEGACY_DATA_RG" --query name -o tsv >/dev/null \
  || warn "Synapse workspace $LEGACY_SYNAPSE not found (skipping Synapse backup will not work)"
az storage account show -n "$LEGACY_STORAGE_ACCT" -g "$LEGACY_DATA_RG" --query name -o tsv >/dev/null \
  || die "Storage account $LEGACY_STORAGE_ACCT not found"
az keyvault show -n "$LEGACY_KV_OEA" -g "$LEGACY_DATA_RG" --query name -o tsv >/dev/null \
  || warn "Key Vault $LEGACY_KV_OEA not found"
if [[ -n "$LEGACY_KV_LMS" ]]; then
  az keyvault show -n "$LEGACY_KV_LMS" --query name -o tsv >/dev/null \
    || warn "Key Vault $LEGACY_KV_LMS not found"
fi
ok "Resources reachable"

step "0.5  Verify AKS cluster running + kubectl works"
CLUSTER_STATE="$(az aks show -n "$LEGACY_AKS" -g "$LEGACY_RG" --query powerState.code -o tsv)"
if [[ "$CLUSTER_STATE" != "Running" ]]; then
  warn "AKS cluster is in state: $CLUSTER_STATE"
  confirm "Start the cluster now?"
  az aks start -n "$LEGACY_AKS" -g "$LEGACY_RG"
fi
az aks get-credentials -n "$LEGACY_AKS" -g "$LEGACY_RG" --overwrite-existing >/dev/null
kubectl get nodes -o name >/dev/null || die "kubectl can't reach the cluster"
ok "AKS reachable: $(kubectl get nodes -o name | wc -l | xargs) node(s)"

step "0.6  Verify MSSQL pod is up"
POD_PHASE="$(kubectl get pod "$MSSQL_POD" -n "$MSSQL_NAMESPACE" -o jsonpath='{.status.phase}' 2>/dev/null || true)"
if [[ "$POD_PHASE" != "Running" ]]; then
  warn "MSSQL pod phase: $POD_PHASE — scaling StatefulSet to 1"
  kubectl scale statefulset/mssql -n "$MSSQL_NAMESPACE" --replicas=1
  kubectl wait --for=condition=Ready "pod/$MSSQL_POD" -n "$MSSQL_NAMESPACE" --timeout=300s
fi
# Probe SQL itself
kubectl exec -n "$MSSQL_NAMESPACE" "$MSSQL_POD" -- /opt/mssql-tools18/bin/sqlcmd -C \
  -S localhost -U sa -P "$MSSQL_SA_PWD" -Q "SELECT @@VERSION" -h -1 >/dev/null \
  || die "sqlcmd failed — wrong sa password? Wrong pod?"
ok "MSSQL pod alive and sa login works"

step "0.7  Enumerate the MSSQL DBs we'll back up"
kubectl exec -n "$MSSQL_NAMESPACE" "$MSSQL_POD" -- /opt/mssql-tools18/bin/sqlcmd -C \
  -S localhost -U sa -P "$MSSQL_SA_PWD" -W -h -1 -Q "
SELECT CONVERT(VARCHAR, DB_NAME(database_id)) + ' | ' +
       CONVERT(VARCHAR, CAST(SUM(size) * 8.0 / 1024 AS DECIMAL(10,1))) + ' MB'
FROM sys.master_files
WHERE database_id > 4
GROUP BY database_id
ORDER BY DB_NAME(database_id)" | grep -v '^$' | tee "$BACKUP_DIR/mssql-inventory.txt"
ok "Inventory written to $BACKUP_DIR/mssql-inventory.txt"

step "0.8  Verify Docker daemon is up (needed for smoke-restore in 01)"
if ! docker ps >/dev/null 2>&1; then
  die "Docker daemon not reachable. Start Docker Desktop and re-run."
fi
ok "Docker daemon reachable"

step "0.9  Estimate Synapse parquet size"
SAS="$(az storage account generate-sas \
  --account-name "$LEGACY_STORAGE_ACCT" \
  --services bfqt --resource-types sco \
  --permissions rl \
  --expiry "$(date -u -v+1H +%Y-%m-%dT%H:%MZ 2>/dev/null || date -u -d '+1 hour' +%Y-%m-%dT%H:%MZ)" \
  --https-only -o tsv 2>/dev/null || echo "")"
if [[ -n "$SAS" ]]; then
  log "Probing oea/dev/stage3 size (may take a minute)..."
  azcopy list "https://${LEGACY_STORAGE_ACCT}.dfs.core.windows.net/oea/dev/stage3?${SAS}" \
    --machine-readable --output-type=text 2>/dev/null \
    | awk -F'[ ,]+' '/Content Length/ {sum += $4} END {printf "stage3 total: %.1f MB\n", sum/1048576}' \
    | tee "$BACKUP_DIR/synapse-estimate.txt" || true
else
  warn "Could not generate SAS for size probe (skipping)"
fi

echo
ok "PRE-FLIGHT PASSED"
log "Next: ./01-mssql.sh"
