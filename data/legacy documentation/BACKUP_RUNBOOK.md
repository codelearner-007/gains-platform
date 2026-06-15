# Legacy Backup Runbook — Step-by-Step

> Concrete commands to back up every data store legacy has, before we tear down the Azure footprint. Aimed at "follow this top to bottom, no decisions required."
>
> **What we are backing up:**
>
> | Data | Source | Where it goes |
> |---|---|---|
> | All MSSQL DBs (`IdentityService`, `Administration`, `SaaS`, `Reporting`, `LMSService`, `LTI`, `MCTService` if it exists) | MSSQL pod on AKS | `.bak` files |
> | Synapse Delta `stage1/stage2/stage3/` parquet | ADLS Gen2 in storage account `stoea*` | parquet tree copy |
> | Schoology OAuth keys + every other Key Vault secret | `kv-oea-edls1`, `kv-elslms-prod` | encrypted JSON files |
> | Power BI `.pbix` files (per-school workspaces) | Power BI service | downloaded `.pbix` |
> | Synapse pipeline / linked-service JSON | Synapse workspace | git push (`workspace_publish`) |
>
> **Time required:** ~1 working day end-to-end if databases are small (< 8 GB total). Most of it is "wait for the dump to finish."
>
> **Storage need:** ~10–50 GB working space locally; final encrypted bundle goes to off-site (B2 / Glacier / wherever) and is much smaller.

---

## §0 Pre-flight — collect these before you start

Fill in these values in a single `.envrc` or note. **Do NOT commit them anywhere.** Delete the file when the runbook finishes.

```bash
# Azure subscription + resource group
export LEGACY_SUB_ID="f42fd3fb-b245-4ad0-db5e-638ddce500de"
export LEGACY_RG="EdvancelsResourceGroup"
export LEGACY_AKS="EdvancelsAKSCluster"
export LEGACY_ACR="edvancelsregistryeastus2"
export LEGACY_SYNAPSE="syn-oea-edls1"
export LEGACY_STORAGE_ACCT="stoeaedls1"        # confirm via `az storage account list`
export LEGACY_KV_OEA="kv-oea-edls1"
export LEGACY_KV_LMS="kv-elslms-prod"          # confirm exact name

# MSSQL credentials (in EdvanceLearning/README.md — assume rotated by now)
export MSSQL_SA_PWD="<sa password, rotate after backup>"

# Local working dir
export BACKUP_DIR="$HOME/Desktop/PS_P/legacy-backup-$(date +%Y%m%d)"
mkdir -p "$BACKUP_DIR"/{mssql,synapse,keyvault,powerbi,config}
```

**Tools you need locally:**
- `az` (Azure CLI) — `brew install azure-cli`
- `kubectl` — `brew install kubectl`
- `azcopy` — `brew install azcopy`
- `age` (encryption) — `brew install age`
- `pigz` (parallel gzip, optional but faster) — `brew install pigz`

```bash
az login
az account set --subscription "$LEGACY_SUB_ID"
az aks get-credentials -n "$LEGACY_AKS" -g "$LEGACY_RG"
kubectl get pods -n production         # sanity check connection
```

---

## §1 Back up the MSSQL databases

### §1.1 Identify what's running and how big it is

```bash
# List databases on the MSSQL pod
kubectl exec -n production mssql-0 -- /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "$MSSQL_SA_PWD" -W -h -1 \
  -Q "SELECT name FROM sys.databases WHERE database_id > 4 ORDER BY name"

# Get size per DB so you know how much disk you'll need
kubectl exec -n production mssql-0 -- /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "$MSSQL_SA_PWD" -W -Q "
SELECT
  DB_NAME(database_id) AS db,
  CAST(SUM(size) * 8.0 / 1024 AS DECIMAL(10,1)) AS size_mb
FROM sys.master_files
WHERE database_id > 4
GROUP BY database_id
ORDER BY db"
```

Expected list (from `01_edvancelearning_backend.md` §3):
`Administration, IdentityService, SaaS, Reporting, LMSService, LTI, MCTService` (and possibly `GenAI`).

### §1.2 Back up each DB

`BACKUP DATABASE` writes inside the pod first, then we `kubectl cp` out.

```bash
DBS="Administration IdentityService SaaS Reporting LMSService LTI MCTService"

for db in $DBS; do
  echo "=== Backing up $db ==="
  # 1) Write the .bak inside the pod
  kubectl exec -n production mssql-0 -- /opt/mssql-tools/bin/sqlcmd \
    -S localhost -U sa -P "$MSSQL_SA_PWD" \
    -Q "BACKUP DATABASE [$db] TO DISK = '/var/opt/mssql/data/$db.bak' \
        WITH COMPRESSION, INIT, CHECKSUM, STATS=10"

  # 2) Copy it out
  kubectl cp -n production "mssql-0:/var/opt/mssql/data/$db.bak" \
             "$BACKUP_DIR/mssql/$db.bak"

  # 3) Delete from the pod (saves PVC space)
  kubectl exec -n production mssql-0 -- rm "/var/opt/mssql/data/$db.bak"

  # 4) Quick integrity check on the local copy
  ls -lh "$BACKUP_DIR/mssql/$db.bak"
done
```

Skip any DB the SELECT above didn't return.

### §1.3 Verify the `.bak` files actually restore

Spin up a local SQL container, restore one as a smoke test:

```bash
docker run -d --name sql-verify \
  -e ACCEPT_EULA=Y -e MSSQL_SA_PASSWORD='VerifyTest!2026' \
  -p 11433:1433 \
  -v "$BACKUP_DIR/mssql:/backups:ro" \
  mcr.microsoft.com/mssql/server:2022-latest

# Wait ~15s for SQL to start
sleep 15

# Restore IdentityService as the smoke test (most important DB)
docker exec sql-verify /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P 'VerifyTest!2026' \
  -Q "RESTORE FILELISTONLY FROM DISK = '/backups/IdentityService.bak'"

# Full restore
docker exec sql-verify /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P 'VerifyTest!2026' -Q "
RESTORE DATABASE IdentityService FROM DISK = '/backups/IdentityService.bak'
WITH MOVE 'IdentityService' TO '/var/opt/mssql/data/IdentityService.mdf',
     MOVE 'IdentityService_log' TO '/var/opt/mssql/data/IdentityService_log.ldf',
     REPLACE"

# Spot-check a known table
docker exec sql-verify /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P 'VerifyTest!2026' -d IdentityService -Q "
SELECT COUNT(*) FROM AbpUsers"

# If the count matches what prod showed → backup is good
docker rm -f sql-verify
```

Repeat the smoke test on at least one more DB (`LMSService` is the next-most-important).

---

## §2 Back up the Synapse Delta parquet

This is the data lake — `stage1/2/3` parquet files in ADLS Gen2.

### §2.1 Get an account-level SAS token (read-only, 24h)

```bash
EXPIRY=$(date -u -v+24H +%Y-%m-%dT%H:%MZ)   # macOS syntax
# Linux: EXPIRY=$(date -u -d "+24 hours" +%Y-%m-%dT%H:%MZ)

SAS=$(az storage account generate-sas \
  --account-name "$LEGACY_STORAGE_ACCT" \
  --services bfqt --resource-types sco \
  --permissions rl --expiry "$EXPIRY" \
  --https-only -o tsv)

echo "SAS valid until $EXPIRY"
```

### §2.2 Copy the parquet trees

```bash
# stage3 (the cubes) — most important
azcopy copy \
  "https://${LEGACY_STORAGE_ACCT}.dfs.core.windows.net/oea/dev/stage3?${SAS}" \
  "$BACKUP_DIR/synapse/stage3" \
  --recursive --log-level=INFO

# stage2 Refined (dim + fact tables after pseudonymisation)
azcopy copy \
  "https://${LEGACY_STORAGE_ACCT}.dfs.core.windows.net/oea/dev/stage2/Refined?${SAS}" \
  "$BACKUP_DIR/synapse/stage2-refined" \
  --recursive --log-level=INFO

# stage2 Ingested (typed CSV-equivalent Delta) — optional, smaller value
azcopy copy \
  "https://${LEGACY_STORAGE_ACCT}.dfs.core.windows.net/oea/dev/stage2/Ingested?${SAS}" \
  "$BACKUP_DIR/synapse/stage2-ingested" \
  --recursive --log-level=INFO

# stage1 Transactional (raw landed CSV→Delta) — optional;
# we have the source CSVs in pre_landing already
azcopy copy \
  "https://${LEGACY_STORAGE_ACCT}.dfs.core.windows.net/oea/dev/stage1?${SAS}" \
  "$BACKUP_DIR/synapse/stage1" \
  --recursive --log-level=INFO
```

If the OEA setup used the separate per-stage containers (`stage1`, `stage2`, `stage3` as top-level containers instead of paths inside `oea`):

```bash
for c in stage1 stage2 stage3; do
  azcopy copy \
    "https://${LEGACY_STORAGE_ACCT}.dfs.core.windows.net/$c?${SAS}" \
    "$BACKUP_DIR/synapse/$c-container" \
    --recursive --log-level=INFO
done
```

### §2.3 Verify a parquet file reads

```bash
cd /Users/mac/Desktop/PS_P/gains-platform/backend
./venv/bin/python - <<'PYEOF'
import pyarrow.parquet as pq, glob, os
root = os.path.expanduser("~/Desktop/PS_P/legacy-backup-$(date +%Y%m%d)/synapse/stage3")
# Find any parquet file under stage3
sample = next(iter(glob.glob(f"{root}/**/*.parquet", recursive=True)), None)
if sample is None:
    print("NO PARQUET FOUND")
else:
    t = pq.read_table(sample)
    print(f"Sample file: {sample}")
    print(f"Rows: {t.num_rows}  Cols: {t.num_columns}")
    print(f"Schema: {t.schema}")
PYEOF
```

If the schema looks like a real cube row — backup is good.

---

## §3 Back up Key Vault secrets

```bash
for kv in "$LEGACY_KV_OEA" "$LEGACY_KV_LMS"; do
  echo "=== Vault: $kv ==="
  mkdir -p "$BACKUP_DIR/keyvault/$kv"

  # List then export each secret as JSON (name + value + tags)
  az keyvault secret list --vault-name "$kv" --query "[].name" -o tsv | \
    while read -r s; do
      az keyvault secret show --vault-name "$kv" --name "$s" \
        --query "{name:name,value:value,tags:tags,contentType:contentType,attributes:attributes}" \
        -o json > "$BACKUP_DIR/keyvault/$kv/$s.json"
      echo "  · $s"
    done
done

# Encrypt the whole keyvault folder — DO NOT leave plaintext on disk
age -p -o "$BACKUP_DIR/keyvault.age" \
    <(tar c -C "$BACKUP_DIR" keyvault)
rm -rf "$BACKUP_DIR/keyvault"

# Verify it decrypts (will prompt for the same passphrase)
age -d "$BACKUP_DIR/keyvault.age" | tar tv | head -20
```

The two **must-have** secrets for the new platform's eventual scraper:
- `schoologyConsumerKeydev`
- `schoologyOauthSignaturedev`

After backup, eyeball-find them in the encrypted bundle and also copy into 1Password / whatever password manager the team uses.

---

## §4 Back up the Power BI `.pbix` files

Power BI doesn't have a CLI for this. **Manual but quick (5-10 min per workspace).**

For each per-school workspace at https://app.powerbi.com:

1. Open the workspace
2. Click the report (each per-school workspace usually has 1-3 reports)
3. **File → Save a copy → Download `.pbix`**
4. Save to `$BACKUP_DIR/powerbi/<school-slug>/<report-name>.pbix`

```bash
mkdir -p "$BACKUP_DIR/powerbi"/{athenian,crestwell,southprep,brightview,centralflorida}
# Then drop the downloaded .pbix files into the right folders
```

Each `.pbix` is ~5-50 MB and includes the embedded Roles table (RLS).

If anyone has Power BI Service Admin rights, the bulk-export REST API works too:
```bash
# Requires Power BI service principal with TenantAdmin.Read.All
# https://learn.microsoft.com/en-us/rest/api/power-bi/admin/reports-get-reports-as-admin
```

But the manual download is faster for 5 schools.

---

## §5 Back up Synapse pipeline / notebook / linked-service definitions

These are already in the `workspace_publish` git branch of the OEA repo. Confirm and push:

```bash
cd "/Users/mac/Desktop/PS_P/gains legacy/OEA"
git branch -a | grep workspace_publish        # Confirm branch exists
git checkout workspace_publish
git log --oneline -5                          # Confirm last sync date
git push origin workspace_publish             # Make sure remote has it

# Tarball a static copy too, in case the remote vanishes later
tar czf "$BACKUP_DIR/synapse/workspace_publish.tar.gz" \
        --exclude='.git' .
git checkout main      # or whatever branch you were on
```

If the workspace_publish branch is empty / outdated, force-sync it from Synapse Studio:

1. Synapse Studio → Manage → Git configuration → "Publish"
2. This pushes the current workspace state to `workspace_publish`
3. Then re-run the `git push` + tarball above

---

## §6 Back up the appsettings / k8s manifests / `gains legacy/` repo itself

These are already in the `gains legacy/` folder on disk. Just zip it as a single belt-and-suspenders bundle:

```bash
cd /Users/mac/Desktop/PS_P
tar c \
  --exclude='node_modules' --exclude='bin' --exclude='obj' \
  --exclude='.git/objects/pack' \
  -C "gains legacy" . | pigz > "$BACKUP_DIR/config/gains-legacy-repo.tar.gz"

ls -lh "$BACKUP_DIR/config/gains-legacy-repo.tar.gz"
```

(You said earlier you didn't want this on local — skip this section if so. The git remote serves the same purpose.)

---

## §7 Catalog everything you just backed up

Generate a manifest so future-you knows what's in the bundle.

```bash
cat > "$BACKUP_DIR/MANIFEST.md" <<EOF
# Legacy Gains Backup
Captured: $(date -u +%Y-%m-%dT%H:%M:%SZ)
Operator: $(whoami)
Source subscription: $LEGACY_SUB_ID

## Contents

### mssql/
$(ls -1 "$BACKUP_DIR/mssql" 2>/dev/null | sed 's/^/- /')

### synapse/
$(find "$BACKUP_DIR/synapse" -maxdepth 1 -type d ! -path "$BACKUP_DIR/synapse" 2>/dev/null | xargs -n1 basename | sed 's/^/- /')

### keyvault.age
Encrypted bundle of Key Vault secrets. Passphrase in 1Password under "Legacy Azure Backup 2026-MM-DD".
Must-have secrets included:
- schoologyConsumerKeydev
- schoologyOauthSignaturedev

### powerbi/
$(ls -1 "$BACKUP_DIR/powerbi" 2>/dev/null | sed 's/^/- /')

### synapse/workspace_publish.tar.gz
Static snapshot of Synapse pipeline / linked-service / notebook JSON.
Also pushed to git remote on \`workspace_publish\` branch.

### config/gains-legacy-repo.tar.gz
Whole \`gains legacy/\` source tree (excludes \`.git/objects/pack\`, \`node_modules\`, \`bin\`, \`obj\`).

## Sizes
$(du -sh "$BACKUP_DIR"/* | sed 's/^/- /')

## Verification done
- Restored \`IdentityService.bak\` to a throwaway Docker SQL — confirmed AbpUsers row count
- Restored \`LMSService.bak\` to same — confirmed K12Standard row count
- Read one parquet file from \`stage3/\` — confirmed schema
- Decrypted \`keyvault.age\` and listed entries — confirmed Schoology keys present

## Restore notes
- MSSQL: see §1.3 of BACKUP_RUNBOOK.md
- Synapse parquet: open directly with pyarrow / spark / duckdb
- Power BI: open .pbix in Power BI Desktop
EOF

cat "$BACKUP_DIR/MANIFEST.md"
```

---

## §8 Push the bundle off-site

**Pick one** (or two for paranoia):

### §8.1 Backblaze B2 — cheapest

```bash
b2 sync "$BACKUP_DIR" "b2://gains-legacy-backup/$(basename $BACKUP_DIR)/"
# ~$0.006/GB/month — a 50 GB bundle costs $3.60/year
```

### §8.2 Cloudflare R2 — almost free with egress amnesty

```bash
rclone sync "$BACKUP_DIR" "r2:gains-legacy-backup/$(basename $BACKUP_DIR)/"
# $0.015/GB/month, no egress fees
```

### §8.3 AWS S3 Glacier Deep Archive — for "never touch again"

```bash
aws s3 sync "$BACKUP_DIR" "s3://gains-legacy-backup/$(basename $BACKUP_DIR)/" \
    --storage-class DEEP_ARCHIVE
# $0.00099/GB/month — 50 GB = $0.60/year. Restore takes 12+ hours.
```

### §8.4 External SSD — physical off-site

Cheapest one-time cost. Buy a 1 TB Samsung T7 (~$80), `rsync` the bundle to it, label it, lock it in a drawer.

---

## §9 Tear-down

Once §1–§8 are done **and verified** (the verification steps in each section, plus the manifest in §7):

1. **Delete the local `$BACKUP_DIR`** — it has secrets in plaintext (the .bak files contain user password hashes, etc.).
   ```bash
   rm -rf "$BACKUP_DIR"
   ```

2. **Proceed to the shutdown sequence** in `AZURE_SHUTDOWN_AUDIT.md` §4 (the 9-step Azure shutdown).

3. **Document where the off-site bundle lives** in the new platform's `docs/runbooks/legacy-backup.md`:
   - Backup location (B2 / R2 / Glacier path)
   - Decryption passphrase location (1Password item name)
   - When it was captured
   - Manifest summary

---

## §10 If something goes wrong mid-run

| Failure | Recovery |
|---|---|
| `kubectl exec` fails: pod not running | `kubectl scale --replicas=1 statefulset/mssql -n production && wait 60s` |
| `BACKUP DATABASE` fails: disk full | Free space on the PVC, OR run one DB at a time and `rm` between |
| `azcopy` fails: SAS expired | Re-generate, re-run — `azcopy` resumes incomplete transfers |
| `azcopy` fails: permission denied | The SAS scope was too narrow — regenerate with `--services bfqt --resource-types sco` |
| Smoke restore fails on the .bak | Re-run `BACKUP` with `WITH CHECKSUM` and retry. If still bad: the source DB has corruption; run `DBCC CHECKDB` on it |
| `age` encryption asks for a passphrase but you forgot to set one | Restart from §3 — the `-p` flag prompts interactively, type a strong passphrase, write it in 1Password before pressing enter |

---

## §11 Estimated time and cost (for planning)

| Step | Time | Cost |
|---|---|---|
| §0 Pre-flight | 15 min | $0 |
| §1 MSSQL (7 DBs, ~5 GB total) | 30–60 min | $0 |
| §2 Synapse parquet (~10–30 GB) | 30–90 min (network bound) | $0 (read-only egress on Hot tier) |
| §3 Key Vault | 10 min | $0 |
| §4 Power BI (5 schools × 1-3 reports) | 30 min manual clicking | $0 |
| §5 Synapse JSON git push | 5 min | $0 |
| §6 Repo tarball | 10 min | $0 |
| §7 Manifest | 5 min | $0 |
| §8 Off-site upload (50 GB to B2 over fiber) | 60–120 min | $4/year for B2, $0.60/year for Glacier |
| §9 Verify + tear down | 30 min | $0 |
| **Total** | **4–6 hours active work** | **< $5/year ongoing** |

Verification is the part that takes the most thought. The actual data movement is mostly idle waiting.
