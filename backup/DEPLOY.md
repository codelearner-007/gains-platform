# Deploying the backup service

The backup service is a **separate Railway service** in the same project as
`backend` and `scraper`, built from this directory. It is a one-shot job, not
a server: it dumps the database, uploads to R2, emails a summary, and exits.
That is why its Railway config differs from the backend's -- and why it needs
`deploy.cronSchedule` at all, which neither `backend` nor `scraper` sets.

| | backend | scraper | backup |
|---|---|---|---|
| shape | long-running HTTP server | one-shot job that exits | one-shot job that exits |
| `startCommand` | `uvicorn …` | `node schoology-exporter.js --help` (inert) | `python backup.py --help` (inert) |
| `healthcheckPath` | `/health` | none — nothing to health-check | none — nothing to health-check |
| `restartPolicyType` | `ON_FAILURE` | `NEVER` | **`NEVER`** |
| `cronSchedule` | none | none (manual only, for now) | `0 9 * * *` (09:00 UTC daily) |

### The start command is deliberately inert

`startCommand` runs `python backup.py --help` and exits 0. It does **not**
back up the database.

That is not laziness — a Railway deploy *runs* the container, so any real
command here means **every deploy performs a real backup run**. `--help`
exits 0 immediately and proves nothing more than "the image builds and the
container starts, with `pg_dump` on `PATH`."

Turning on unattended execution is a separate, deliberate, reviewable commit
that changes this string to the real invocation (`python backup.py`) — never
a dashboard-level override. A service-level start command set through the
Railway dashboard or API does **not** win over this file (`scraper/DEPLOY.md`
verified this twice for its own service, once by accident); overriding it
there to something else does not work either. The committed value in
`railway.json` is the only one that matters.

`restartPolicyType: NEVER` is the second important one. A one-shot backup job
that exits non-zero should stay failed and be looked at, not auto-restarted
by Railway into re-running `pg_dump` + the R2 upload — wasting the cycle and
potentially masking that today's backup never actually succeeded.

Because Railway's cron trigger **skips** (does not queue) a new run while the
previous one is still executing, a hung job silently costs a missed day with
no automatic catch-up and no failure email (there is nothing running to send
one). `BACKUP_PGDUMP_TIMEOUT_MS` / `BACKUP_UPLOAD_TIMEOUT_MS` force a hang to
fail fast and free up tomorrow's slot, but a missed day is still only caught
by a human noticing no email arrived or checking the R2 bucket.

## Creating the service (one time)

In the existing **Gains Platform** Railway project:

1. New Service → GitHub Repo → the same repo already used for `backend` /
   `scraper`.
2. Settings → **Root Directory: `backup`** (this makes Railway pick up
   `backup/railway.json` and `backup/Dockerfile`, exactly like `backend`'s and
   `scraper`'s Root Directory settings).
3. Settings → **Deploy on push**: leave disabled (or set explicitly) while the
   service is new, so a merge to `main` doesn't immediately fire a build+deploy
   cycle that hasn't been verified yet.
4. Add the variables below.
5. Deploy once with `cronSchedule` already set in `railway.json` and
   `startCommand` still inert — this proves the image builds and the
   container starts before anything unattended runs on a schedule.
6. Run the verification steps in `docs/backup-service-technical-plan.md`
   Section 6 (unit tests, `--dry-run` locally, a manual `railway run`, forcing
   the failure path, confirming `restartPolicyType: NEVER` behavior) before
   trusting the cron trigger unattended.

## Variables

Set on the **backup** service (never in the repo):

| Variable | Value |
|---|---|
| `DATABASE_URL` | Supabase Supavisor **session-mode** pooler connection string — not the direct host, not the transaction-mode pooler |
| `R2_ACCOUNT_ID` | Cloudflare account ID |
| `R2_ACCESS_KEY_ID` | R2 API token access key ID, scoped to Object Read & Write on the single target bucket |
| `R2_SECRET_ACCESS_KEY` | matching R2 API token secret |
| `R2_BUCKET` | target R2 bucket name, e.g. `gains-platform-backups` |
| `R2_BACKUP_PREFIX` | key prefix, e.g. `backups/` — must match the R2 lifecycle rule's scoped prefix exactly |
| `BACKUP_RETENTION_COUNT` | how many most-recent backups to keep in R2 — enforced by the app after every successful run, not by the R2 lifecycle rule |
| `BACKUP_PGDUMP_TIMEOUT_MS` | wall-clock limit on `pg_dump`, default `1800000` |
| `BACKUP_UPLOAD_TIMEOUT_MS` | wall-clock limit on the R2 upload, default `1200000` |
| `BACKUP_TMP_DIR` | local scratch dir for the dump file, optional |
| `BACKUP_LOG_LEVEL` | `info` normally; `debug` when investigating a failed run |
| `BACKUP_NOTIFY_EMAILS` | who gets the run summary — comma/semicolon/whitespace separated. Empty disables email |
| `RESEND_API_KEY` | Resend key. Required once `BACKUP_NOTIFY_EMAILS` is set |
| `BACKUP_NOTIFY_FROM` | verified Resend sender address |
| `BACKUP_NOTIFY_ON` | `always` (default) or `failure`. FATAL/FAILED always send |

### Notifications

Every run emails a summary: the verdict (`OK` / `FAILED` / `FATAL`), the
dump size and duration, the R2 key, and the failing step's error when the run
didn't succeed. It is sent from `main()`'s own `finally`, so it goes out even
when the run aborts before completing the upload — which is exactly when
nobody would otherwise find out.

Two deliberate behaviours, same as `scraper`'s notification design:

* A mail outage **never** changes the run's exit code. Send errors are
  logged and swallowed — `send_run_summary()` never raises.
* Recipients configured **without** `RESEND_API_KEY` / `BACKUP_NOTIFY_FROM`
  logs an **ERROR**. Silently sending nothing while an operator believes
  alerts are on is worse than not configuring it at all.

## Running it

**Manual, before trusting the cron schedule.** Use the Railway CLI from a
machine linked to the project — this runs the real command against the
service's actual Railway-injected environment variables, without waiting for
the cron trigger and without touching `startCommand`:

```bash
railway run --service backup python backup.py --dry-run
railway run --service backup python backup.py
```

`--dry-run` validates config and R2/Postgres connectivity (`pg_dump
--version`, `check_bucket_access()`) without writing a dump file or uploading
anything. Confirm the object landed in R2 (`Cloudflare dashboard → R2 →
bucket → backups/<date>/`) and that the summary email arrived before relying
on the schedule.

**Scheduled (cron).** `deploy.cronSchedule` in `railway.json` is already set
to `"0 9 * * *"` (09:00 UTC daily — Railway cron schedules are always
interpreted in UTC, with no DST adjustment). Once the manual verification
above has passed, the next scheduled UTC trigger is the real first automated
run — watch its logs and confirm the email arrives without any manual
trigger.

Note the consequence once `startCommand` is ever changed from `--help` to the
real invocation for a genuinely unattended cron setup: from then on every
non-cron deploy of this service *also* performs a real backup run, exactly
like `scraper`'s equivalent warning. Keep this in mind before merging any
change that touches `backup/railway.json`.

## What a run does — and deliberately does not do

It runs `pg_dump -Fc --no-owner --no-privileges` against `DATABASE_URL`,
writes the dump to a local temp file, uploads it to
`<R2_BACKUP_PREFIX><date>/gains-platform-<run_id>.dump`, deletes the local
temp file in a `finally` regardless of outcome, and emails the run summary.

After a successful run, it also deletes the oldest backup(s) in R2 beyond
`BACKUP_RETENTION_COUNT` most-recent ones (see
`docs/backup-service-technical-plan.md` Section 1's `prune_old_backups()`
description) — an R2 Object Lifecycle Rule is optional now, a defense-in-depth
backstop rather than the primary retention mechanism (Section 5). It also does
**not** attempt any restore or verification of the dump it
produced — a periodic manual restore drill is recommended separately and is
explicitly out of scope here.

## Verifying a run

Check the Railway deployment logs for the run's `run_id`, then confirm the
object exists in R2:

```bash
aws s3 ls s3://<bucket>/backups/<date>/ \
  --endpoint-url https://<account-id>.r2.cloudflarestorage.com
```

Exit codes: `0` clean · `1` the dump or upload failed, or another caught
error occurred · `2` bad CLI usage.
