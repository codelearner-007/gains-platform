# Azure Legacy Shutdown — Minimal Backup & Sunset Plan

> **Goal:** retire the legacy Azure footprint (.NET Captures app + Synapse pipeline + Power BI) and keep only what the new Next.js + FastAPI + Supabase platform needs. No school is using legacy.
>
> **Constraint** (per user): Azure Blob Storage **stays running** — the new platform reads the same `pre_landing/Schoology/` CSVs. Do NOT back it up, just keep it live.
>
> **Sources:**
> - `gains legacy/docs/research/00_overview.md` … `06_top_level_docs.md`
> - `gains legacy/docs/Jan 2026 - Azure Usage.xlsx`, `Feb 2026 - Azure Usage.xlsx`
> - `gains legacy/EdvanceLearning/k8s/*.yaml`

---

## §0 TL;DR

What we actually need from legacy → new app: **two small things.** Everything else gets deleted.

| Backup item | Why it matters to new app | Size | Where it lives now |
|---|---|---|---|
| **Schoology OAuth consumer key + secret** | New app's scraper / `dim_question_data` refresh needs them | ~1 KB | `kv-oea-edls1` secrets `schoologyConsumerKeydev` + `schoologyOauthSignaturedev`; also in `scraper/.env` |
| **`LMSService.K12Standard` + CASE Network entity rows (CSV export)** | Sanity-check the new platform's `dim_standard` covers everything legacy had (the $10k/yr CASE Network membership lapsed; legacy DB is the last authoritative copy) | ~1–5 MB | MSSQL pod, DB `LMSService` |

Everything else is either (a) already in git, (b) already mirrored in the new platform, or (c) zero value going forward.

**Cost cut: ~$1,800/month → ~$5/month** (just Blob storage we're keeping).

---

## §1 What we keep running

| Resource | Why |
|---|---|
| Azure Blob storage account (whatever holds `oea/pre_landing/Schoology/`) | New platform reads raw CSVs from here. Tier stays Hot. |
| The Schoology scraper (or its replacement in the new app) writing to that container | The pipeline depends on fresh CSVs landing. |

Nothing else.

---

## §2 The only two backups we need

### §2.1 Schoology OAuth credentials

```bash
# Extract the two secrets that the scraper depends on
az keyvault secret show --vault-name kv-oea-edls1 \
  --name schoologyConsumerKeydev --query value -o tsv \
  > backup/schoology_consumer_key.txt

az keyvault secret show --vault-name kv-oea-edls1 \
  --name schoologyOauthSignaturedev --query value -o tsv \
  > backup/schoology_oauth_signature.txt

# Encrypt before storing anywhere
age -p backup/schoology_*.txt -o backup/schoology-creds.age
shred -u backup/schoology_*.txt
```

Plus copy `gains legacy/scraper/.env` (already on disk) somewhere off the legacy machine. That file has the same values plus the Azure SAS for the storage account — useful for the scraper migration.

**Store these in:** the new platform's secret manager (Supabase Vault, GitHub Actions secrets, Doppler — wherever the new app already keeps its env). They're already needed by the new app's ingest job; this isn't really a "backup," it's a one-time credential handoff.

### §2.2 `LMSService.K12Standard` + CASE Network tables — CSV dump

The new platform's `dim_standard` is seeded by `supabase/seeds/refresh_standards.py`. Before we trust that seed and shut down legacy, verify it covers every row legacy had.

```bash
# 1) Scale up the MSSQL pod if it was scaled to zero
kubectl scale --replicas=1 statefulset/mssql -n production
kubectl wait --for=condition=Ready pod/mssql-0 -n production --timeout=180s

# 2) Export the tables that hold standards data
kubectl exec -n production mssql-0 -- /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "$LEGACY_SA_PWD" -d LMSService -W -s ',' -Q \
  "SELECT * FROM K12Standard"           > backup/legacy-K12Standard.csv

# Same for the LMS module's CASE Network mirror tables (only the ones with
# data — most are stubs). The ones likely populated:
for tbl in CFItem CFAssociation CFItemAssociation CFPackage CFDocument; do
  kubectl exec -n production mssql-0 -- /opt/mssql-tools/bin/sqlcmd \
    -S localhost -U sa -P "$LEGACY_SA_PWD" -d LMSService -W -s ',' -Q \
    "SELECT * FROM $tbl" > "backup/legacy-$tbl.csv"
done

# 3) Compare counts vs new platform
psql "$NEW_SUPABASE_URL" -c \
  "SELECT COUNT(*) AS new_dim_standard FROM dim_standard"
wc -l backup/legacy-K12Standard.csv
```

If the new platform is light on rows, merge the missing rows into `supabase/seeds/dim_standard.csv` (or wherever the seed reads from) and re-run the seed.

**If the counts already match (within reason)** — discard the CSV. Don't ship a dead-weight backup just for the sake of it. The new platform's standards refresh is the canonical source going forward.

---

## §3 What we do NOT back up (and why)

| Skipped item | Why it's safe to skip |
|---|---|
| Azure Blob `pre_landing/` CSVs | Per user — staying live, new app reads from it |
| Synapse `stage1`/`stage2`/`stage3` parquet (Delta cubes) | Derivable from `pre_landing/` by new platform's transformation chain (`backend/app/transformations/01_staging` → `09_cubes`) |
| Synapse Serverless SQL `ldb_dev_s*` DBs | These are just external-table views over the parquet — zero data of their own |
| MSSQL `Administration`, `SaaS`, `Reporting`, `LTI`, `MCTService` DBs | ABP framework tables / tenant routing / LTI handshake — no school is using legacy, no rows worth preserving |
| MSSQL `IdentityService` DB | No active users on legacy. New platform uses Supabase Auth — fresh accounts |
| Power BI PBIX files | Already decoded into `data/_pbix_extract/` (layouts, measures, DAX). Visual layout already mirrored in new React reports |
| ACR `edvancelsregistryeastus2` images | Legacy app is dead — no reason to keep ability to redeploy it |
| Synapse pipeline JSON / linked services | Already in git on the `workspace_publish` branch in `gains legacy/OEA/`. Plus we have the audit docs in `docs/audit/` |
| `.NET appsettings.*.json` | Already in `gains legacy/` repo (and on git history) |
| k8s manifests | Same — already in `gains legacy/EdvanceLearning/k8s/` |
| Azure Monitor / Log Analytics history | Logs about a decommissioned app have no forward value |
| Key Vault secrets (non-Schoology ones) | OpenAI keys, MCT JWT, PBI service-principal — all should be rotated and discarded, not preserved |

---

## §4 Shutdown order (Azure Resource Group `EdvancelsResourceGroup`)

Each step pauses-and-observes. Reversible until step 9 (final RG delete).

| # | Action | What stops | Savings/mo (Feb 2026 actuals) |
|---|---|---|---|
| 0 | Rotate `sa` SQL password, Schoology OAuth keys, PBI SP secret, Azure OpenAI keys (all committed plaintext per `00_overview.md §7.2`) — once you've captured §2.1, treat the old values as compromised | none | $0 |
| 1 | Capture the §2.2 export — start the MSSQL pod, run the CSV dump, scale back down | none | $0 |
| 2 | Disable all Synapse triggers (storage-event triggers on `success.txt`) so no pipeline runs even if a stray CSV lands | pipeline runs | ~$200 |
| 3 | Pause Spark pool `spark3p3sm` (Synapse Studio → Manage → Apache Spark pools → Pause) | Spark compute autoscale | ~$400 |
| 4 | Power BI: delete the per-school workspaces and let the Pro/Premium capacity lapse | PBI | $587 |
| 5 | AKS: `az aks stop -n EdvancelsAKSCluster -g EdvancelsResourceGroup` (NOT delete — stop, so we can restart for 15 minutes if something is missed) | All .NET pods, MSSQL pod, RabbitMQ | $180 |
| 6 | Wait 7 days. If no one yells, continue. | — | — |
| 7 | Delete Synapse workspace `syn-oea-edls1` (workspace deletion does NOT delete the ADLS data — Blob stays intact) | Synapse baseline | ~$50 residual |
| 8 | Delete: ACR `edvancelsregistryeastus2`, Azure Monitor / App Insights for the retired services, Key Vault `kv-elslms-prod` (after Schoology keys captured), Key Vault `kv-oea-edls1` (same) | ACR + monitor + KV | ~$12 |
| 9 | Final cleanup: delete the AKS cluster (`az aks delete ...`), delete the resource group leftovers if any. **Do NOT delete the storage account holding `pre_landing/`** — that's our keep-resource. | residual VMs / disks / LBs | ~$180 |

**End state:** one storage account, one container (`oea`), one path (`pre_landing/Schoology/`). Maybe ~$5–10/mo depending on data volume and replication tier.

---

## §5 Pre-shutdown sanity checks (run these first)

1. **Confirm new platform ingests the same raw CSV path:**
   ```bash
   # In gains-platform backend
   grep -rn "pre_landing\|oea/Schoology" backend/app/jobs/ | head -5
   ```
   Should resolve to the same Blob URL the legacy scraper writes to.

2. **Confirm new platform can read at least one school's full year:**
   ```bash
   # Pick an assessment from 2025-26 session, run it through the new pipeline,
   # and verify the KPIs match the legacy PBIX numbers (already done for the
   # 5 reports we shipped — but spot-check a fresh assessment to be sure).
   ```

3. **Confirm `dim_standard` row count is in range:**
   ```bash
   psql "$NEW_SUPABASE_URL" -c "SELECT COUNT(*) FROM dim_standard"
   # Compare against the §2.2 CSV export count
   ```

4. **Confirm Schoology scraper credentials work from new platform:**
   - Drop the OAuth keys from §2.1 into the new platform's env
   - Run one scrape against the existing Schoology tenant — confirm CSV lands in Blob

If all four pass, you're safe to start the shutdown.

---

## §6 Open questions before I write a day-by-day runbook

1. **Is the legacy scraper still running** and writing to `pre_landing/`, or already paused? (If running, repoint or replace before disabling Synapse triggers — step 2.)
2. **Where does the new platform's Schoology ingest run from?** Vercel cron / Railway worker / something else? Needs the OAuth keys from §2.1 once the legacy KV is gone.
3. **`dim_standard` vs legacy `K12Standard`** — should I just run the comparison now and report the row-count delta, so we know whether the §2.2 export is even needed?
4. **Do you want the legacy `gains legacy/` repo itself archived** to long-term storage (it has all the source code + configs + appsettings)? The repo is the most complete backup of legacy short of the live databases.

Answer those four and I'll convert this into a literal day-by-day cutover checklist.
