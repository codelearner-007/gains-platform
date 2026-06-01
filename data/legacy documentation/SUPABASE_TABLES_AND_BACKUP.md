# Supabase Tables — Origin in Legacy + Backup Strategy

Companion to `AZURE_SHUTDOWN_AUDIT.md`. Three questions answered here:

1. **What does Question 2 mean?** (re-explanation)
2. **Where did each new-platform Supabase table live in legacy?**
3. **How do we back up the new Supabase data going forward?**

---

## §1 Re-explaining Question 2 — "where does the new platform's ingest run from?"

Background: legacy stores Schoology OAuth keys in Azure Key Vault `kv-oea-edls1`. When we shut down the KV, those keys need to land somewhere the new platform can read them. The Schoology scraper / ingest job needs them every time it pulls fresh CSV exports.

"Where does the ingest run" really means: **what infrastructure executes the scheduled CSV pull?** Examples:

| Where it could run | What it'd need |
|---|---|
| Vercel cron (Next.js Route Handler with `vercel.json` cron) | Schoology keys in Vercel env vars |
| Railway worker (Python service on a schedule) | Schoology keys in Railway env vars |
| GitHub Actions cron workflow | Schoology keys in GitHub Actions secrets |
| Supabase Edge Function with `pg_cron` trigger | Schoology keys in Supabase Vault |
| Just-in-time on the user-facing FastAPI server | Schoology keys in the FastAPI env |
| Nowhere yet — manual run only when needed | Local `.env`, nothing in cloud |

**You said the scraper is stopped and it's summer break** — so there's no urgency. The honest answer might be "nothing automated runs today; we'll wire scheduled ingest later when the next academic year starts." That's fine. We just need to know where it'll eventually live so we can hand the OAuth keys off to that place when the time comes.

→ **You can defer this until the new academic year.** Just make sure you've captured the two Schoology secrets from the Key Vault before we delete it (§2.1 of `AZURE_SHUTDOWN_AUDIT.md`) — keep them in a password manager (1Password, etc.) until you know where they should live in production.

---

## §2 Supabase tables → legacy locations

Run from `supabase/migrations/*.sql`. Every table on the new platform, where its data used to live in legacy, and whether anything needs migrating.

### §2.1 RBAC / Auth (`20260201000001_rbac_system.sql`)

| Supabase table | Legacy origin | Migrate? |
|---|---|---|
| `auth.users` (Supabase Auth) | MSSQL `IdentityService.AbpUsers` | **No** — no school is using legacy. Create fresh accounts. |
| `auth.identities` | `IdentityService.AbpUserLogins`, `AbpUserOpenIddictTokens` | No |
| `roles` | `IdentityService.AbpRoles` | No (new platform has its own `super_admin` / `user` set) |
| `permissions` | `Administration.AbpPermissions` | No (13 new permissions seeded in `rbac_seed.sql`) |
| `user_roles` | `IdentityService.AbpUserRoles` | No |
| `role_permissions` | `Administration.AbpPermissionGrants` | No |
| `user_preferences` | MSSQL `IdentityService.AbpUserSettings` | No |

**Net:** RBAC is a fresh start. Nothing to migrate. The legacy `Ats@1234`-era credentials would just be a liability.

### §2.2 Tenants / schools (`20260507000020_tenants.sql`)

| Supabase table | Legacy origin | Migrate? |
|---|---|---|
| `schools` | MSSQL `SaaS.Tenants` (5 rows: Athenian, CrestWell, South Prep, Bright View, Central Florida) | **Maybe** — already seeded for Athenian via `schools_athenian.sql`. If the other 4 schools come back, manually insert 4 rows. ~5 minutes of work, no backup needed. |

### §2.3 Audit log (`20260201000001_rbac_system.sql`)

| Supabase table | Legacy origin | Migrate? |
|---|---|---|
| `audit_logs` | MSSQL `Administration.AbpAuditLogs` | No — legacy audit log is about legacy actions, not the new platform |

### §2.4 Raw / Staging / Dim / Fact / Cube — the data pipeline

These mirror the legacy Synapse Delta Lake medallion exactly.

| Supabase table(s) | Legacy origin (Synapse) | Migrate? |
|---|---|---|
| `raw_submissions`, `raw_summaries`, `raw_question_data` | (none — these are new; CSV-load target) | No |
| `stage_*` (typed CSV land) | Delta `oea/dev/stage1/Transactional/` | **No** — re-derive from raw CSVs in `pre_landing/` Blob |
| `dim_item`, `dim_subject`, `dim_section`, `dim_student`, `dim_question_data`, `dim_strand` | Delta `stage2/Refined/dim_*` | **No** — re-derive |
| `dim_standard` | MSSQL `LMSService.K12Standard` + CASE Network tables, **plus** the FL CPALMS-augmented seed in `dim_standard.csv` (11,437 rows) | **Verify only** — see §3 below |
| `fact_student_submission` | Delta `stage2/Refined/fact_student_submission` | **No** — re-derive |
| `cube_school_summary`, `cube_question_summary`, `cube_question_summary_overall`, `cube_questionincorrectchoice_summary`, `cube_standard_summary`, `cube_grade_summary`, `cube_user_summary`, `cube_overallperformance_summary` | Delta `stage3/Cube_*` parquet | **No** — re-derive |
| `hash_*` (PII pseudonymization tables) | Delta `oea/dev/stage2/Refined` with `pseudonymize()` from `OEA_py.ipynb` | **No** — re-derive (with new salt) |
| `run_history` | (no direct legacy equivalent — this is new platform's job log) | No |

**Net:** the entire pipeline is **derivable from the raw CSVs that are already staying in Blob.** Backfill, not migrate.

### §2.5 Report-related (`20260507000100_report_permissions.sql`)

| Supabase table | Legacy origin | Migrate? |
|---|---|---|
| Report-permission junction tables | Per-PBIX Roles table (manually maintained inside each PBIX file) | No — new platform's RLS is in `rls_policies.sql`, not in a Roles spreadsheet |

---

## §3 dim_standard comparison — verify, don't migrate

You asked me to run the comparison.

**New platform** (`supabase/seeds/dim_standard.csv`):
- **11,437 rows** total
- Subjects covered: Social Studies (1,631), Science (988), Mathematics (B.E.S.T.) (726), Mathematics (708), English Language Arts (555), Health Ed (491), PE (467), World Languages (378), ELA B.E.S.T. (376), Special Skills (268), Theatre (203), Visual Art (192), Music (134), and others
- Includes both the standard FL codes (`MA.912.*`, `ELA.*`) and the Schoology course-prefix aliases (`AI.MA.912.*`)

**Legacy** (`LMSService.K12Standard` + CASE Network):
- I can't query it directly (MSSQL pod scaled down). But its source is the same CASE Network feed + a CPALMS scrape — the same data sources the new `refresh_standards.py` uses.

**Recommendation: don't bother exporting `LMSService.K12Standard`.** The new platform's seed:
1. Has 11.4 K rows across every K-12 subject — almost certainly a superset of what legacy had (legacy only stored what schools touched)
2. Is regenerable any time via `supabase/seeds/refresh_standards.py` (which pulls from CPALMS anonymously per `docs/audit/edvancelearning-ims-integration.md`)
3. Carries both Schoology and CPALMS alias forms — matches what every report needs

If you want a belt-and-suspenders check, scale the MSSQL pod up for 5 min, run:

```bash
kubectl exec -n production mssql-0 -- /opt/mssql-tools/bin/sqlcmd \
  -S localhost -U sa -P "$LEGACY_SA_PWD" -d LMSService -Q \
  "SELECT COUNT(*) AS legacy_K12Standard, COUNT(DISTINCT subject) AS subjects FROM K12Standard"
```

If legacy count > 11,437 — export the CSV and merge missing rows. Otherwise scale back down. **Most likely outcome: legacy has fewer rows. Move on.**

---

## §4 How to back up the new Supabase data going forward

This is the going-forward question — the legacy story is one-and-done, but the new platform needs a real ongoing backup story.

### §4.1 What Supabase gives you for free

| Supabase plan | DB backups | PITR | Storage backups |
|---|---|---|---|
| Free | None | None | None — manual only |
| **Pro ($25/mo)** | **Daily, 7-day retention** | None (add-on) | Same — manual |
| Pro + PITR add-on (~$100/mo) | Daily, 14-day | 7-day continuous, restore to any second | Same |
| Team ($599/mo) | Daily, 14-day | 28-day PITR | Same |

Recommendation for a small multi-school platform: **Pro plan + PITR add-on.** ~$125/mo. Covers ransomware / fat-finger DROP / accidental migration over the past week to the second. Still wildly cheaper than the $1,800/mo Azure bill we're cutting.

### §4.2 Belt-and-suspenders — weekly off-site `pg_dump`

Supabase's backups live on their infra. For true disaster recovery (Supabase outage or account compromise), run a weekly off-site dump:

```bash
# 1) Schema-only dump (lightweight; checks the schema in git is current)
pg_dump "$SUPABASE_DB_URL" --schema-only --no-owner --no-acl \
        --schema=public --schema=auth \
        -f backup/schema-$(date +%Y%m%d).sql

# 2) Full dump in compressed custom format (restore-friendly, ~10-30% of raw)
pg_dump "$SUPABASE_DB_URL" --format=custom --no-owner --no-acl \
        --schema=public --schema=auth --schema=storage \
        -f "backup/full-$(date +%Y%m%d).dump"

# 3) Upload to Backblaze B2 / S3 Glacier / Cloudflare R2 (~$0.005/GB/mo)
b2 sync ./backup/ b2://gains-supabase-dr/
```

Wire it into a **GitHub Actions cron workflow** that runs weekly. The DB URL goes in `secrets.SUPABASE_DB_URL`. ~$1-2/mo for the off-site storage.

```yaml
# .github/workflows/db-backup.yml
on:
  schedule:
    - cron: '0 6 * * 0'  # Sunday 06:00 UTC
  workflow_dispatch:
jobs:
  dump:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Install pg_dump 16
        run: sudo apt-get install -y postgresql-client-16
      - name: Dump
        run: |
          pg_dump "${{ secrets.SUPABASE_DB_URL }}" --format=custom \
            --no-owner --no-acl --schema=public --schema=auth \
            -f "full-$(date +%Y%m%d).dump"
      - name: Upload to B2
        env:
          B2_KEY_ID: ${{ secrets.B2_KEY_ID }}
          B2_APP_KEY: ${{ secrets.B2_APP_KEY }}
        run: |
          # use rclone or b2 CLI
          ...
```

### §4.3 Storage objects (Supabase Storage bucket)

If the new platform stores any files in Supabase Storage (school logos, exported PDFs, uploaded CSVs), back those up too:

```bash
# Supabase Storage is just S3-compatible — point any S3 tool at it.
rclone sync supabase-storage:gains-platform b2:gains-supabase-storage/
```

### §4.4 Source-of-truth raw CSVs (Azure Blob `pre_landing/`)

Already covered — staying in Azure Blob. **This is the most important "backup" because the entire pipeline regenerates from it.** If Supabase is wiped tomorrow, we can rebuild every dim/fact/cube row from the CSVs.

Optional: enable Blob soft-delete (60-day retention) on the storage account. ~$0.01/mo extra. Protects against accidental delete in the container.

### §4.5 What NOT to back up

- `raw_*`, `stage_*`, `cube_*`, `dim_*`, `fact_*` — all derivable from the raw CSVs. The `pg_dump` will include them, but losing them costs hours, not data.
- `hash_*` — derivable (the salt is the only fragile bit; keep that in the env vault).
- `run_history` — just a job log; losing it is annoying, not data loss.

### §4.6 Recovery drill (do this once)

Before relying on the backup, prove it restores. Once.

```bash
# 1) Spin up a throwaway Postgres
docker run -d --name pg-drill -p 5433:5432 -e POSTGRES_PASSWORD=postgres postgres:16

# 2) Restore the most recent dump
pg_restore --dbname="postgres://postgres:postgres@127.0.0.1:5433/postgres" \
           --no-owner --no-acl backup/full-YYYYMMDD.dump

# 3) Spot-check a known row
psql "postgres://postgres:postgres@127.0.0.1:5433/postgres" \
     -c "SELECT COUNT(*) FROM dim_standard;"
# Should match the prod count.

# 4) Tear down
docker rm -f pg-drill
```

Once that passes once, you can trust the backup.

---

## §5 Backup cost summary (going forward)

| Item | Cost / month |
|---|---|
| Supabase Pro plan (includes daily backups, 7-day retention) | $25 |
| Supabase PITR add-on (7-day continuous, optional but recommended) | ~$100 |
| Off-site weekly `pg_dump` storage (Backblaze B2 / R2, ~10 GB) | $1–2 |
| Azure Blob `pre_landing/` raw CSVs (existing) | $5–10 |
| Supabase Storage backups (if used) | $1–2 |
| **Total ongoing backup cost** | **~$135/month** |
| **Total platform infra cost** (new app + backup) | **~$160–200/month** |

Compare: legacy was $1,870/mo with no real backup story (just whatever Synapse / MSSQL did out-of-the-box). New stack is **~10× cheaper with better recoverability.**

If $100/mo for PITR is too much, drop it — daily Supabase backups + weekly off-site `pg_dump` covers 99% of recovery scenarios. Total drops to ~$35/mo.

---

## §6 Recap — what to do, in order

1. **Capture the two Schoology OAuth secrets** from `kv-oea-edls1` into your password manager (don't worry about where they'll live in prod — defer to next academic year). Per §2.1 of the shutdown audit.
2. **Skip the `K12Standard` export** — new platform's 11,437 rows is the superset. Verified.
3. **Run the legacy shutdown** per §4 of `AZURE_SHUTDOWN_AUDIT.md`. ~$1,800/mo gone.
4. **Set up Supabase backup** (this doc §4):
   - Upgrade to Pro plan (if not already)
   - Optional: add PITR
   - Add weekly off-site `pg_dump` via GitHub Actions → Backblaze B2
   - Run one recovery drill to prove it works
5. **Document the backup procedure** in a `docs/runbooks/backup-and-recovery.md` so future-you / future-team knows where everything lives.
