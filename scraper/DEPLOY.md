# Deploying the scraper

The scraper is a **separate Railway service** in the same project as `backend`,
built from this directory. It is a one-shot job, not a server: it runs, exports,
uploads, notifies the backend, and exits. That is why its Railway config differs
from the backend's.

| | backend | scraper |
|---|---|---|
| shape | long-running HTTP server | one-shot job that exits |
| `startCommand` | `uvicorn …` | `node schoology-exporter.js --school <name>` |
| `healthcheckPath` | `/health` | none — nothing to health-check |
| `restartPolicyType` | `ON_FAILURE` | **`NEVER`** |

`restartPolicyType: NEVER` is the important one. On `ON_FAILURE`, a scrape that
exits non-zero (which now happens on partial upload failure) would be restarted
by Railway and would re-export everything — hammering Schoology and duplicating
objects in the bucket. A job that fails should stay failed and be looked at.

## Creating the service (one time)

In the existing **Gains Platform** Railway project:

1. New Service → GitHub Repo → `Edvance-Learning/gains-platform`
2. Settings → **Root Directory: `scraper`** (this makes Railway pick up
   `scraper/railway.json` and `scraper/Dockerfile`)
3. Settings → disable **Deploy on push** if you do not want every merge to `main`
   to fire a scrape. Recommended while the schedule is still manual.
4. Add the variables below.

## Variables

Set on the **scraper** service (never in the repo):

| Variable | Value |
|---|---|
| `SCHOOLOGY_CREDENTIALS` | `{"default":{"username":"…","password":"…","consumer_key":"…","consumer_secret":"…"}}` |
| `SUPABASE_URL` | the prod Supabase URL |
| `SUPABASE_SERVICE_KEY` | prod service-role key — the `schoology-ingest` bucket has **zero** RLS policies, so only the service role can write it |
| `BACKEND_BASE_URL` | the backend service's public URL |
| `INGESTION_TRIGGER_SECRET` | **must be byte-identical to the backend's**, or every call 401s |
| `SCRAPER_CONCURRENCY` | `1` while the Transfer-History fix soaks |
| `SCRAPER_LOG_LEVEL` | `info` normally; `debug` when investigating a failed run |
| `SCRAPER_NOTIFY_EMAILS` | who gets the run summary — comma/semicolon/whitespace separated. Empty disables email |
| `RESEND_API_KEY` | Resend key. Required once `SCRAPER_NOTIFY_EMAILS` is set |
| `SCRAPER_NOTIFY_FROM` | verified sender address |
| `SCRAPER_NOTIFY_ON` | `always` (default) or `failure`. FATAL/FAILED always send |

### Notifications

Every run emails a summary: the verdict (`OK` / `PARTIAL` / `NO-DATA` / `FAILED` /
`FATAL`), per-school counts, and each actionable failure with its reason. It is
sent from a `finally`, so it goes out even when the run aborts because the backend
was unreachable — which is exactly when nobody would otherwise find out.

Two deliberate behaviours:

* A mail outage **never** changes the run's exit code. Send errors are logged and
  swallowed.
* Recipients configured **without** `RESEND_API_KEY`/`SCRAPER_NOTIFY_FROM` logs an
  **ERROR**. Silently sending nothing while an operator believes alerts are on is
  worse than not configuring it at all.

### Reading the logs

Lines are `ISO-8601  LEVEL  [runId | school | a=assessmentId]  message | k=v`.
WARN and ERROR go to **stderr**, so they can be split or alerted on separately.

The line to look for when a run finds nothing is the funnel:

```
WARN  [.. | Athenian] discovery found NO assessments — funnel breakdown follows | courses=106 …
      outsideDueWindow=3 futureDated=3 …
WARN  [.. | Athenian] 3 assessment(s) are due AFTER the window — re-run with --due-until …
```

That breakdown accounts for every dropped assessment, so "0 discovered" is never
ambiguous between a quiet day and a broken config.

`INGESTION_TRIGGER_SECRET` is currently **unset on the backend**, which means the
trigger endpoint fails closed and rejects everything. Generate one
(`openssl rand -hex 32`) and set the same value on both services.

## Running it

**Manual (current mode).** The service has no `cronSchedule`, so it only runs when
triggered:

```bash
railway run --service scraper node schoology-exporter.js --school Athenian --dry-run
railway run --service scraper node schoology-exporter.js --school Athenian
```

Locally, name the script explicitly — the image uses `CMD`, not `ENTRYPOINT`:

```bash
docker run --rm --env-file .env gains-scraper \
  node schoology-exporter.js --school Athenian --dry-run
```

`CMD` is deliberate. Railway's custom start command *replaces* `CMD`, but with an
`ENTRYPOINT` set it is appended as arguments instead, yielding
`node schoology-exporter.js node schoology-exporter.js --school X`. That happens to
work when the arguments arrive separately and breaks when the platform wraps them
in `sh -c`, because the flags then collapse into a single argv string and
`--school` stops matching. `CMD` behaves correctly under both.

Per-run flags — the control surface for "which school, which assessments":

| flag | purpose |
|---|---|
| `--school <name>` | which school (substring of the school name) |
| `--dry-run` | discovery only: no browser, no export, no upload, no trigger |
| `--assessment <text>` | only assessments whose title contains this |
| `--window-days <n>` | override the school's `due_date_window_days` |
| `--due-until <YYYY-MM-DD>` | extend the window forward to catch **future-dated** assessments |
| `--include-undated` | include assessments with no due date at all |

The last two matter more than they look: an assessment dated in the future, or
with no due date, is invisible to the default window. That is the usual reason a
run reports "0 assessments" when the assessment plainly exists.

**Scheduled (later).** Once a real run has been signed off, add a schedule in
Railway → service → Settings → Cron Schedule, e.g. `0 7 * * *` (07:00 UTC / 03:00
ET, after the school day). Railway then runs the container on that schedule using
`startCommand`. Start with one school.

Keep runs serialised. Schoology's Transfer History is a single per-account page,
so two concurrent scrapes on the same identity interleave their exports.

## What a run does — and deliberately does not do

It uploads CSVs to `schoology-ingest` under the frozen key

```
<short_name>/<session>/<category>/<subject>/<grade>/<section>/<original-filename>.csv
```

then POSTs `/api/v1/ingestion/scraper-complete`. The backend worker lands the raw
rows and **stops**.

It does **not** rebuild the warehouse, and it cannot. Production holds a populated
`fact_student_submission` over an empty `raw`/`stg`, and every transform is
`TRUNCATE + INSERT` — so a rebuild there would repopulate fact from whatever a
single scrape landed and destroy every report.

That is prevented **in code, unconditionally**, by the §HISTORIC invariant in
`backend/app/transformations/runner.py`: every `(school, session)` slice is
fingerprinted before and after a build, and any slice the raw layer cannot
regenerate must come out byte-identical or the whole run rolls back. It needs no
configuration and there is no flag to bypass it — verified in both directions
(a prod-shaped rebuild is refused; a full-raw rebuild is not).

`INGESTION_TRANSFORMS_ENABLED=false` on prod remains sensible — there is nothing to
gain by attempting a rebuild on a serving box — but it is an efficiency setting,
not the safeguard. Flipping it on by mistake is survivable.

Getting new data into prod *reports* is a separate, still-unsolved problem — see
`docs/audit/fixes/03_prod_data_sync_runbook.md`.

## Verifying a run

```sql
SELECT run_id, status, files_processed, rows_inserted, error_count
FROM ingestion_runs ORDER BY started_at DESC LIMIT 3;
```

`landed` with `error_count = 0` is success. Files are then archived to
`processed/<short_name>/<run_id>/`, so a re-trigger is a clean no-op.

Exit codes: `0` clean · `1` a school failed **or** partially uploaded · `2` bad CLI usage.
