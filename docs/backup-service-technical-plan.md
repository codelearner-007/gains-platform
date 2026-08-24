# Backup Service — Technical Implementation Plan

Status: PLAN ONLY. No code in this document, and none should be written until this
plan is reviewed and approved. Companion to `docs/backup-scheduler-plan.md` (the
plain-English version) — this is the same project one level down, detailed enough
to hand to an implementer.

Written in **Python 3.12**, mirroring the conventions already proven out in
`backend/` (structured logging via the standard `logging` module, `pydantic-settings`
for config, `requirements.txt` pinned exactly like `backend/requirements.txt`,
`ruff`/`black`/`mypy` settings in `pyproject.toml`, `pytest` for tests) rather than
`scraper/`'s Node.js style — this service has nothing in common with `scraper`'s
Playwright/browser-automation job, and the repo's existing Python conventions are
the closer fit. It ships as a one-shot script (not a FastAPI app — no HTTP server,
no `uvicorn`), its own Railway service in the same Railway project as `backend`
and `scraper`, a Resend-based run-summary email sent from a `finally` block, an
inert Railway `startCommand`, and `restartPolicyType: NEVER`.

**Dump strategy decision — temp file, not streaming, for v1.** Two options were
weighed:

1. **Temp file on the Railway container's local disk (chosen for v1).** `pg_dump`
   writes to a local file (e.g. `/tmp/gains-<date>.dump`) inside the running
   container; the upload step reads that file; the file is deleted and the
   container shuts down when the job ends — nothing persists on Railway between
   runs regardless. Caveat: the container needs enough disk (Railway's ephemeral
   `/tmp`) to hold the whole compressed dump — worth confirming the actual dump
   size before committing to this (Section 7).
2. **Stream straight through** — pipe `pg_dump`'s stdout directly into a
   multipart R2 upload, never touching disk. No disk requirement at all, but the
   final size isn't known until the upload finishes, and a mid-stream failure
   can leave a partial multipart upload in R2 that needs an abort/lifecycle rule
   to clean up.

**Decision: option 1 for v1.** It's simpler, it lets the job verify the dump's
byte size before upload and report a size the code has actually confirmed (not
an in-flight guess) in the success email — which the plan already promises — and
it lets a failed upload be retried from the same file without re-running
`pg_dump`. Move to streaming (option 2) only if the dump grows large enough to
outgrow the container's temp space; see Section 7 for the concrete trigger and
the switch-over notes.

**Reuse decision — mirror the pattern, not the code.** `scraper` is Node.js and
this service is Python, so its `lib/notify.js` / `lib/logger.js` files cannot be
imported directly — reuse here means `lib/notify.py` / `lib/logger.py`
deliberately copy scraper's *design decisions*, not its source. Specifically
carried over: the Resend REST call shape and its `timeout`, `redact()`'s
approach to masking secrets before a log line or email body is built, the
recipient-parsing/classification rules, the never-throws contract on the
send-summary function (a Resend outage must never crash or mask the job's real
result), and the "verdict first, in the subject line" email convention. What
stays deliberately separate per service: env var names (`BACKUP_*` vs.
`SCRAPER_*`), the summary object's fields (this service has no
schools/assessment-funnel data), and each service's own test suite —
`scraper/lib/notify.js` and `scraper/lib/logger.js` are not touched by this
plan.

---

## 1. Directory / File Listing — `backup/`

Files in the new `backup/` directory:

- `requirements.txt`
- `pyproject.toml`
- `backup.py`
- `lib/__init__.py`
- `lib/logger.py`
- `lib/notify.py`
- `lib/pg_dump.py`
- `lib/r2_upload.py`
- `tests/test_logger.py`
- `tests/test_notify.py`
- `tests/test_pg_dump.py`
- `tests/test_r2_upload.py`
- `Dockerfile`
- `railway.json`
- `.env.example`
- `.gitignore`
- `README.md`
- `DEPLOY.md`

**`requirements.txt`** — new, pinned exact versions the same way
`backend/requirements.txt` is. Dependencies: `boto3` (S3-compatible client, used
against R2's S3 API), `httpx` (Resend REST calls — already the HTTP client
`backend` standardizes on), `pydantic-settings` (env var loading/validation, same
as `backend/app/core/config.py`), `python-dotenv` (local-dev `.env` loading only —
a no-op on Railway, where env vars are injected directly). Deliberately **no**
`fastapi`/`uvicorn` (this is a one-shot script, not a web server), **no**
`sqlalchemy`/`asyncpg` (it shells out to `pg_dump` against the Postgres wire
protocol directly, never opens its own DB connection), and **no**
`supabase`/`playwright` (no Supabase client SDK use, no browser automation).

**`pyproject.toml`** — new, same three tool sections as
`backend/pyproject.toml` (`[tool.black]`, `[tool.ruff]`, `[tool.mypy]`, identical
`line-length`/`target-version` values for consistency across the repo's Python
services) plus a `[tool.pytest.ini_options]` block mirroring backend's
(`testpaths = ["tests"]`, `python_files = "test_*.py"`, `addopts = "-v
--import-mode=importlib --cov=lib --cov-report=html"` — no `asyncio_mode`, since
this service has no async code).

**`backup.py`** — new. The single-file main entry point: CLI arg parsing up top
(via `argparse`), a `main()` wrapped in `try/except/finally`, `send_run_summary()`
called from the `finally` block, `sys.exit(code)` called once at the very end
rather than scattered through `main()`. Orchestrates: CLI parsing → preflight →
dump → upload → cleanup → exit. See Section 2 for the exact sequence.

**`lib/logger.py`** — new, structured logging modeled on
`backend/app/core/logging_config.py`'s `JSONFormatter` (same field shape:
`timestamp` via `datetime.now(timezone.utc).isoformat()` — never
`datetime.utcnow()`, per this repo's standing rule — `level`, `logger`,
`message`, plus `exception` when `exc_info` is set). Extends that pattern with
two things `backend`'s web-request logger doesn't need: a `run_id` field
attached to every record (via a `logging.LoggerAdapter` bound at startup, the
Python equivalent of the Node plan's `.child()` context binding), and a
`redact()` helper — a regex set that masks connection strings, API keys, and
access-key-style tokens before they reach a log line, since this service's env
vars (`DATABASE_URL`, `R2_SECRET_ACCESS_KEY`, `RESEND_API_KEY`) are exactly the
kind of value that must never appear in plaintext logs. Log level configurable
via `BACKUP_LOG_LEVEL` (`debug | info | warning | error`), read the same way
`backend`'s `LOG_LEVEL` setting is.

**`lib/notify.py`** — new. `send_run_summary()` never raises — every exception
inside it is caught and logged, so a Resend outage can never mask the backup's
real result or crash `backup.py`'s `finally` block. Sends via a direct `httpx`
POST to Resend's REST API (`https://api.resend.com/emails`) with a
`timeout=15.0`, `redact()` (from `lib/logger.py`) applied to subject and body
before send. Recipient parsing: `split_recipients()` /
`classify_recipients()` / `is_address()`, splitting on comma/semicolon/whitespace
and validating each with a simple regex (or `email-validator`, already a pinned
`backend` dependency, reused here for consistency rather than hand-rolling
validation). Failure taxonomy: no-recipients configured → INFO (not an error —
the run still logs normally), recipients-configured-but-no-`RESEND_API_KEY` →
ERROR, provider non-2xx response → ERROR + swallowed, network error → ERROR +
swallowed. Summary fields the body renders: `run_id`, `started_at`,
`duration_sec`, `dry_run`, `database_host` (host only, parsed out of
`DATABASE_URL`, never the full connection string — it carries a password),
`dump_bytes`, `dump_duration_sec`, `upload_duration_sec`, `r2_bucket`, `r2_key`,
`cleanup` (the `prune_old_backups()` result dict, or `None` when cleanup was
never attempted), `fatal_error` (`{name, message}`, set only when the run
aborted before producing a dump or before completing the upload). The body
always renders a "Retention:" line stating the configured
`BACKUP_RETENTION_COUNT` limit, present on every run outcome (success,
failure, dry-run) regardless of whether cleanup itself ran. Alongside it, the
body renders a "Cleanup:" line in one of three states: skipped (dry-run or
fatal_error), a failure state (listing failed, or one or more deletes
failed — naming the key(s) and whether any other deletes still succeeded),
or a success state (either the deleted keys or "nothing to delete"), each
also folding in the resulting post-prune backup count so the line states
both what happened this run and how many backups remain in R2.
`overall_status()` returns one
of three values: `OK`, `FAILED` (dump or upload step raised), `FATAL`
(unexpected/unhandled error). Subject line format:
`[GAINS backup] <STATUS> — <dump_bytes formatted> — <duration_sec>s` +
`" (dry-run)"` when applicable — verdict first, in the subject.

**`lib/pg_dump.py`** — new. Spawns `pg_dump` via `subprocess.run` (never
`shell=True` — arguments passed as a list, so a multi-GB dump is never buffered
through a shell string, and there's no shell-injection surface even though the
inputs are our own env vars) with flags `-Fc --no-owner --no-privileges
--file=<tmp path>` against `DATABASE_URL`, writing the dump to a local file
under `BACKUP_TMP_DIR` (default `tempfile.gettempdir()`) — the chosen v1
strategy (see the decision note at the top of this document and Section 7 for
the streaming alternative and its trigger condition). Captures stderr into a
bounded buffer for the failure-email text, and enforces a hard wall-clock
timeout via `BACKUP_PGDUMP_TIMEOUT_MS` (`subprocess.run(..., timeout=...)`,
which sends `SIGKILL` to the child on expiry — see Section 7's cron
skip-not-queue risk for why this matters). Returns a small `PgDumpResult`
dataclass (`file_path`, `bytes`, `duration_ms`) on exit code 0 — `bytes` read via
`os.stat` on the completed file, so `summary.dump_bytes` reflects a size the
code has actually confirmed, not an in-flight estimate; raises a tagged
`PgDumpError` (`.stage = "pg_dump"`) otherwise, carrying the last N lines of
captured stderr in `.stderr_tail` for the notification email. Verifies `pg_dump
--version` is on `PATH` (via `shutil.which`) before spawning the real dump, so a
missing/broken binary fails fast with a clear message instead of a cryptic
`FileNotFoundError`.

**`lib/r2_upload.py`** — new. Wraps `boto3.client("s3", endpoint_url=
f"https://{R2_ACCOUNT_ID}.r2.cloudflarestorage.com", region_name="auto", ...)`
with credentials from `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY`, and
`boto3`'s built-in `TransferConfig`-driven multipart upload (via
`upload_file()` — handles multipart chunking automatically, no custom code, per
verified fact #5) to stream the completed local dump file to `R2_BUCKET` —
`boto3` reads the file off disk in chunks itself, so upload memory usage stays
flat regardless of dump size. Because the file's full size is already known at
this point (`lib/pg_dump.py` resolved it via `os.stat`), a failed upload can be
retried against the same file without re-running `pg_dump`. Writes to
`R2_BUCKET` under a dated key:
`<R2_BACKUP_PREFIX>YYYY-MM-DD/gains-platform-<run_id>.dump` (prefix default
`backups/`, exactly matching the plain-English plan's example key). Enforces its
own timeout (`BACKUP_UPLOAD_TIMEOUT_MS`) by running the upload in a background
thread and joining it with a timeout, since `boto3`'s S3 client has no built-in
overall-operation timeout for a multipart transfer (only a per-HTTP-call
`connect_timeout`/`read_timeout` via `botocore.config.Config`, which this also
sets as a floor). Exposes a small `check_bucket_access()` helper (a
`head_bucket()` call) used only by `--dry-run`, to validate R2
credentials/bucket/network reachability without transferring any data.
Also exposes `list_backup_keys(settings, timeout_ms=10_000) -> list[str]` —
all object keys under `R2_BACKUP_PREFIX` in `R2_BUCKET`, oldest-first by S3
`LastModified` (via `client.get_paginator("list_objects_v2")`, so it handles
more than 1000 objects) — and `prune_old_backups(settings, keep, log,
timeout_ms=10_000) -> dict`, which deletes the oldest backups beyond `keep`
most-recent ones, clamping `keep` to a minimum of 1 so the backup just
uploaded (always the newest) can never be deleted. `prune_old_backups()`
never raises — a listing failure or a per-key delete failure is caught and
reported in the returned `{"attempted", "deleted", "errors", "list_error",
"remaining"}` dict instead, since it runs after the backup has already
succeeded and must not turn a successful run into a failed one. `"remaining"`
is the post-prune backup count (`None` when `list_error` is set, since the
true count is unknown if listing itself failed).

**`Dockerfile`** — new, structurally modeled on `backend/Dockerfile` (`FROM
python:3.12-slim`, `apt-get install` for the one native dependency it needs,
`COPY requirements.txt` + `pip install` before `COPY . .` for layer caching,
same comment density explaining *why* each line exists). Content differs
because the native dependency differs: `backend`'s Dockerfile installs
`gcc libpq-dev` to build `psycopg2`; this service instead needs a `pg_dump`
binary whose major version matches the target Supabase project's Postgres major
version (flagged in Section 7 as needing verification at implementation time,
per research fact #2) — installed from the official PGDG apt repository
(Debian's own repo only ships one Postgres client major at a time and it may
not match), with the `<MAJOR>` value pinned as a Dockerfile `ARG` so bumping it
is a one-line, reviewable diff. `COPY requirements.txt .` + `pip install
--no-cache-dir -r requirements.txt` before `COPY . .`, same layering as
`backend`. `CMD ["python", "backup.py"]`, not `ENTRYPOINT`, for the same reason
`backend`'s Dockerfile uses `CMD` (Railway custom-start-command concatenation).

**`railway.json`** — new, same four top-level shape as `backend/railway.json`
(`$schema`, `build.builder: "DOCKERFILE"`, `build.dockerfilePath: "Dockerfile"`,
`deploy.{startCommand,restartPolicyType,numReplicas}`) plus one new field:
`deploy.cronSchedule`. See Section 4 for the exact value and rationale. No
`healthcheckPath` (that's specific to `backend`'s long-running HTTP server; this
is a one-shot job that exits, so Railway has nothing to health-check).

**`.env.example`** — new, same section-comment style as `backend/.env.example`
(a `# ── Heading ──` banner per group, inline comments explaining
default/required/optional and how each var is consumed). Full variable list in
Section 3.

**`.gitignore`** — new, Python-flavored (`__pycache__/`, `*.pyc`, `.venv/`,
`.env`, any local tmp/download directory — here `BACKUP_TMP_DIR`'s default
scratch location), mirroring `backend/.gitignore`'s shape rather than
`scraper/.gitignore`'s Node-flavored one.

**`tests/test_logger.py`** — new, written against `lib/logger.py`. Covers:
level filtering, `redact()` masking connection strings/API keys/access keys,
the `run_id`-bound adapter attaching `run_id` to every record, stdout routing,
and the JSON field shape matching `backend`'s `JSONFormatter` conventions.

**`tests/test_notify.py`** — new, using `pytest`'s fixture/mocking pattern
(injecting a fake `httpx` transport via `httpx.MockTransport`, or monkeypatching
the module-level client, rather than hitting the network) — same technique the
Node plan used, adapted to Python's `httpx` testing idioms. Covers: recipient
parsing/classification, `overall_status()` mapping for all three statuses,
`OK`/`failure`-policy suppression, missing-`RESEND_API_KEY` ERROR path,
provider-rejection path, network-error path, and the "no recipients is INFO not
ERROR" distinction.

**`tests/test_pg_dump.py`** — new. Does **not** invoke a real `pg_dump` against
a live database (no network dependency in unit tests). Instead: (a) verifies
the argument list `pg_dump` is spawned with (`-Fc --no-owner --no-privileges
--file=...`) given a fake `DATABASE_URL`, by monkeypatching
`subprocess.run`; (b) verifies the timeout path — spawn a fixture child process
(e.g. `python -c "import time; time.sleep(999)"`) with a short
`BACKUP_PGDUMP_TIMEOUT_MS`, assert it raises `PgDumpError` with `.stage ==
"pg_dump"` after `subprocess.TimeoutExpired`; (c) verifies stderr tail capture
on non-zero exit; (d) verifies `PgDumpResult(file_path, bytes, duration_ms)` is
returned correctly against a fixture file, with `bytes` matching `os.stat`.

**`tests/test_r2_upload.py`** — new. Uses `botocore.stub.Stubber` (the standard
`boto3` testing tool — no real network/R2 credentials needed) to mock the S3
client's `upload_file`/`head_bucket` calls. Covers: the upload called with the
correct file path and dated key (`backups/YYYY-MM-DD/gains-platform-<run_id>.dump`),
the upload-timeout path actually raising when the background upload thread
doesn't finish in time, and `check_bucket_access()` surfacing a clear error on
a `head_bucket()` failure.

**`README.md`** — new, mirrors `backend/README.md`'s structure (what the
service does, one paragraph; `pip install -r requirements.txt` + `cp
.env.example .env` setup; a variable table with one-line purposes).

**`DEPLOY.md`** — new, mirrors `scraper/DEPLOY.md`'s structure (the closest
existing precedent for a one-shot Railway job, even though the code itself
mirrors `backend`'s Python conventions): the `backend`/`scraper` vs.
this-service comparison table (shape / startCommand / healthcheckPath /
restartPolicyType), the "start command is deliberately inert" subsection with
the same warning about dashboard-level overrides being ignored, "Creating the
service (one time)" steps, and a variables table for what to set on the Railway
service (not committed to the repo). Section 4 below is the source material for
this file.

---

## 2. Runtime Sequence — `backup.py`

1. `load_dotenv()` (via `python-dotenv`) at the top of `backup.py` — a no-op in
   Railway, where env vars are injected directly; used for local dev only.
2. Parse `sys.argv` via `argparse`: recognized flags are `--dry-run` and
   `--help` (the latter handled automatically by `argparse`, exiting 0 — this
   is the command Railway's `startCommand` invokes on every deploy, Section 4).
   Any unrecognized flag → `argparse` prints usage to stderr and exits 2 (bad
   CLI usage).
3. Generate `run_id` (`uuid.uuid4()`).
4. Construct the root logger via `lib/logger.py`'s setup function, bound with
   `run_id` (a `logging.LoggerAdapter`, the Python equivalent of the Node
   plan's `.child()`).
5. Enter `main()`. A `summary` dict is initialized up front (`{"run_id":
   run_id, "started_at": ..., "dry_run": args.dry_run, "fatal_error": None,
   ...}`), built incrementally so the `finally` block always has *something* to
   email even if the run dies on step 6 or 7.
6. **Preflight validation** (runs in both normal and `--dry-run` mode): confirm
   `DATABASE_URL`, `R2_ACCOUNT_ID`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`,
   `R2_BUCKET` are all set (via `pydantic-settings`' validation at import time,
   so a missing required var fails immediately with a clear message); confirm
   `pg_dump --version` succeeds; call `check_bucket_access()` from
   `lib/r2_upload.py`. Any failure here raises a tagged exception
   (`.stage = "preflight"`) — caught by `main()`'s `except`, `summary["fatal_error"]`
   set, exit code 1.
7. **If `--dry-run`**: log the preflight results, log "dry-run: skipping
   pg_dump and R2 upload", set `summary["dry_run"] = True` with no dump/upload
   figures, skip straight to step 11. Validates config/connectivity, does no
   real work.
8. **Dump step** (`lib/pg_dump.py`): run `pg_dump` against `DATABASE_URL` (the
   Supavisor **session-mode** pooler connection string — see Section 3) writing
   to a local temp file under `BACKUP_TMP_DIR` (default
   `tempfile.gettempdir()`). On success, record `summary["dump_bytes"]`,
   `summary["dump_duration_sec"]`. On failure, the exception propagates to
   `main()`'s `except` — `summary["fatal_error"]` set, exit code path below.
9. **Upload step** (`lib/r2_upload.py`): stream the local dump file to
   `R2_BUCKET` at the dated key. On success, record `summary["r2_bucket"]`,
   `summary["r2_key"]`, `summary["upload_duration_sec"]`. On failure, same as
   step 8 — propagates to `main()`'s `except`. If this step fails, the dump
   file from step 8 is still on disk when a manual re-run reaches this step —
   no need to re-run `pg_dump` first.
9a. **Retention cleanup** (`lib/r2_upload.py`'s `prune_old_backups()`), only
    reached because step 9 succeeded: delete the oldest backups beyond
    `BACKUP_RETENTION_COUNT` most-recent ones in `R2_BUCKET`, recording the
    result in `summary["cleanup"]`. Never raises and never changes the exit
    code — a listing or per-key delete failure is caught and reported inside
    `summary["cleanup"]` for the email body only, since cleanup runs after the
    backup has already succeeded and must not turn a successful run into a
    failed one. Skipped entirely (stays `None`) whenever step 9 didn't run —
    dry-run, or a dump/upload failure.
10. **Cleanup (temp file)**: delete the local temp dump file in a `finally`
    scoped to the dump/upload block (not the outer one), so it runs whether
    upload succeeded or failed — never leaves multi-GB files on the
    container's ephemeral disk once the job actually exits.
11. **`main()`'s own `finally`**: call `send_run_summary(summary, log=root_log)`.
    This is what makes the email fire on every exit path — success, a caught
    dump/upload error, or an uncaught exception that reached `main()`'s
    `except` — because it runs regardless of which branch above set the exit
    code. `send_run_summary()` never raises (Section 1's `lib/notify.py`
    description), so a Resend outage cannot mask the backup's real result.
12. **Exit code determination**, returned from `main()` and passed to
    `sys.exit()` once at the bottom of the module (never `sys.exit()` inside
    `main()` itself, so the `finally` in step 11 is guaranteed to run first):
    - `0` — clean: dump + upload succeeded, or `--dry-run` preflight passed.
    - `1` — dump failed, OR upload failed, OR any other caught error during the
      run ("the backup did not fully complete").
    - `2` — bad CLI usage (unrecognized flag), returned before `main()` is even
      entered (`argparse`'s own exit), so no email is sent for this case
      (nothing ran yet to report on).
13. Outermost `try/except` (wrapping the `main()` call itself, outside its own
    try/except/finally): catches anything `main()`'s own handling didn't — logs
    it and calls `sys.exit(1)` directly, a last-resort guard.

---

## 3. Environment Variables / Secrets — `.env.example`

Grouped exactly like `backend/.env.example` (banner comments per section),
loaded via a `pydantic-settings` `BaseSettings` subclass in `lib/config.py`
mirroring `backend/app/core/config.py`'s pattern.

**Database**
- `DATABASE_URL` — full Postgres connection string to Supabase's **Supavisor
  session-mode pooler** (NOT the direct `db.<ref>.supabase.co` host — IPv6-only,
  unreachable from Railway's IPv4 containers without the paid IPv4 add-on — and
  NOT the port-6543 transaction-mode pooler, which breaks `pg_dump`'s COPY
  semantics). Get the exact string from Supabase Dashboard → Project Settings →
  Database → Connection string → "Session pooler". Still port 5432, different
  hostname than the direct connection. Required.

**Cloudflare R2**
- `R2_ACCOUNT_ID` — Cloudflare account ID; used to build the R2 endpoint URL
  `https://<R2_ACCOUNT_ID>.r2.cloudflarestorage.com`. Required.
- `R2_ACCESS_KEY_ID` — R2 API token access key ID (scoped to Object Read & Write
  on the single target bucket only — see Section 5). Required.
- `R2_SECRET_ACCESS_KEY` — the matching secret. Required.
- `R2_BUCKET` — target bucket name. Required.
- `R2_BACKUP_PREFIX` — key prefix backups are written under (e.g. `backups/`).
  Optional, default `backups/`. Must match the prefix scoped by the R2 lifecycle
  rule (Section 5) or old backups will not auto-expire.
- `BACKUP_RETENTION_COUNT` — how many most-recent backups to keep in
  `R2_BUCKET`, **enforced by the app** (not by an R2 lifecycle rule): after
  every successful run, `prune_old_backups()` deletes the oldest backup(s)
  beyond this count. Optional, default `3`.

**Backup behavior**
- `BACKUP_PGDUMP_TIMEOUT_MS` — hard wall-clock limit on the `pg_dump` step before
  it is killed. Optional, default `1800000` (30 min). Exists specifically to
  bound the "hung job blocks tomorrow's cron trigger" risk (Section 7).
- `BACKUP_UPLOAD_TIMEOUT_MS` — hard wall-clock limit on the R2 upload step.
  Optional, default `1200000` (20 min). Same rationale.
- `BACKUP_TMP_DIR` — local scratch directory for the dump file before upload
  (the chosen v1 strategy — see the decision note at the top of this document).
  Optional, default OS temp dir (`tempfile.gettempdir()`).

**Logging**
- `BACKUP_LOG_LEVEL` — `debug | info | warning | error`, default `info`. Same
  semantics as `backend`'s `LOG_LEVEL` setting (debug adds full stack traces and
  finer-grained step timing).

**Run notifications**
- `BACKUP_NOTIFY_EMAILS` — who hears about every run. Comma/semicolon/whitespace
  separated. Empty disables email entirely (the run still logs normally).
- `RESEND_API_KEY` — Resend API key. Required once `BACKUP_NOTIFY_EMAILS` is set.
- `BACKUP_NOTIFY_FROM` — verified Resend sender address. Required once
  `BACKUP_NOTIFY_EMAILS` is set.
- `BACKUP_NOTIFY_ON` — `always` (default) | `failure` (suppresses OK runs; FATAL
  and FAILED always send regardless).

All secrets live only in Railway service variables on the new `backup` service —
never committed, never shared with the `scraper` or `backend` services' variable
sets even where a name looks reusable (e.g. this service's own `R2_*` keys are
separate from any existing storage credentials).

---

## 4. Railway Service Setup

1. In the existing **Gains Platform** Railway project: **New Service → GitHub
   Repo** → the same repo already used for `backend`/`scraper`.
2. **Settings → Root Directory: `backup`** — this is what makes Railway pick up
   `backup/railway.json` and `backup/Dockerfile` instead of the repo root or
   another service's config, exactly like `backend`'s Root Directory setting.
3. **Settings → Deploy on push**: leave disabled (or set explicitly) while the
   service is new, so a merge to `main` doesn't immediately fire a build+deploy
   cycle you haven't verified yet.
4. `railway.json` fields:
   - `build.builder`: `"DOCKERFILE"`
   - `build.dockerfilePath`: `"Dockerfile"`
   - `deploy.startCommand`: `"python backup.py --help"` — **deliberately inert**:
     a Railway deploy always *runs* the container, so a real command here means
     every deploy performs a real backup. `--help` exits 0 immediately and
     proves nothing more than "the image builds and the container starts."
     Turning on unattended execution is a separate, deliberate, reviewable
     commit that changes this string to the real invocation — never a
     dashboard-level override (a dashboard start-command override is ignored
     while `railway.json` defines one, per `scraper`'s `DEPLOY.md`).
   - `deploy.restartPolicyType`: `"NEVER"` — a one-shot job that fails should
     stay failed and be looked at, not auto-restarted into re-running a backup
     (wasting a `pg_dump` + upload cycle, and potentially masking that today's
     backup never actually succeeded).
   - `deploy.numReplicas`: `1`.
   - `deploy.cronSchedule`: the new field this service adds. Planned value:
     `"0 9 * * *"` — once daily at **09:00 UTC** (Railway cron schedules are
     always interpreted in UTC). Rationale: 09:00 UTC is ~04:00–05:00 US
     Eastern / ~01:00–02:00 US Pacific — solidly inside the school system's
     overnight low-traffic window, after any late-evening activity and well
     before the next school day's usage ramps up, and clear of the scraper's
     own run window so the two jobs are never contending for the same database
     connections at once. Treat the exact hour as a placeholder to confirm
     against actual usage patterns before enabling, not a hard requirement.
   - Minimum interval Railway enforces between cron triggers is 5 minutes,
     irrelevant here at once/day.

   Example `railway.json`:

   ```json
   {
     "$schema": "https://railway.com/railway.schema.json",
     "build": { "builder": "DOCKERFILE", "dockerfilePath": "Dockerfile" },
     "deploy": {
       "startCommand": "python backup.py --help",
       "restartPolicyType": "NEVER",
       "numReplicas": 1,
       "cronSchedule": "0 9 * * *"
     }
   }
   ```

5. Add the environment variables from Section 3 to the service (Railway
   dashboard → Variables), not the repo.
6. **Do not** flip `cronSchedule` live until Section 6's verification steps are
   complete on a real deploy — see Section 6.

---

## 5. Cloudflare R2 Setup (one-time, outside the code)

1. **Create the bucket** (Cloudflare dashboard → R2 → Create bucket). Name it
   something unambiguous, e.g. `gains-platform-backups`. Region: R2 buckets are
   automatically distributed; no region selection needed.
2. **Create a scoped API token** (R2 → Manage API Tokens → Create API Token):
   - Permission: **Object Read & Write**.
   - Scope: the **single target bucket** created in step 1 — not account-wide
     Admin Read & Write. This limits blast radius if the token ever leaks (it
     can only touch this one bucket, not every bucket on the account).
   - Save the generated **Access Key ID** and **Secret Access Key** — these map
     directly to `R2_ACCESS_KEY_ID` / `R2_SECRET_ACCESS_KEY` in Section 3. The
     Secret Access Key is shown once; store it in Railway's variables
     immediately (or a password manager) since Cloudflare will not show it
     again.
   - Note the **Account ID** shown alongside the token — maps to
     `R2_ACCOUNT_ID`.
3. **Configure the Object Lifecycle Rule (optional — defense-in-depth, not the
   primary retention mechanism)** (R2 → bucket → Settings → Object Lifecycle
   Rules → Add rule): the app itself now enforces retention — after every
   successful run, `prune_old_backups()` deletes the oldest backup(s) beyond
   `BACKUP_RETENTION_COUNT` (Section 3), so this rule is no longer what "the
   plan already promises" for normal-case retention. Still worth keeping as a
   backstop in case app-level pruning silently breaks:
   - Scope: prefix `backups/` (must match `R2_BACKUP_PREFIX` from Section 3
     exactly, including the trailing slash).
   - Action: expire objects after a long window (e.g. 90 days) — long enough
     to never fire under normal operation, only as a safety net.
4. Confirm pricing expectations (research fact #7): Standard storage
   $0.015/GB-month, 10GB-month free tier, free egress. A daily dump with the
   app pruning down to `BACKUP_RETENTION_COUNT` (3) backups after every
   successful run should land near-zero to a few dollars/month depending on
   database size — worth a rough sanity check against the actual DB size once
   the first real dump exists, not before.

---

## 6. Verification / Testing Plan (before enabling the real cron schedule)

Order matters — each step should pass before moving to the next.

1. **Unit tests** (no network, no real credentials): write and pass
   `tests/test_logger.py`, `tests/test_notify.py`, `tests/test_pg_dump.py`,
   `tests/test_r2_upload.py` as described in Section 1. Run `pytest` from
   `backup/`. All must be green before any real-service testing begins.
2. **`--dry-run` locally**: `cp .env.example .env`, fill in real
   `DATABASE_URL` (session pooler) and real R2 credentials pointing at the
   actual bucket, run `python backup.py --dry-run`. Confirm: preflight passes
   (`pg_dump --version` found, `DATABASE_URL` parses, `check_bucket_access()`
   succeeds against the real bucket), no dump file is created, no object is
   written to R2, exit code 0, and — if `BACKUP_NOTIFY_EMAILS` is set — a
   dry-run summary email arrives.
3. **`--dry-run` with a deliberately broken credential**: temporarily set an
   invalid `R2_SECRET_ACCESS_KEY` (or point `DATABASE_URL` at a wrong host) and
   re-run `python backup.py --dry-run`. Confirm preflight fails fast with a
   clear, correctly-`redact()`-ed error message (no secret value leaked into
   the log line) and exit code 1. Restore the correct value afterward.
4. **Manual first real run**: after the Railway service exists (Section 4)
   with `cronSchedule` still set but *before* trusting it unattended, use the
   Railway CLI from a machine linked to the project: `railway run --service
   backup python backup.py` (runs the real command against the service's
   actual Railway-injected environment variables, without waiting for the cron
   trigger and without touching `startCommand`). Watch the logs stream live.
5. **Confirm the object landed in R2**: after step 4, check the Cloudflare
   dashboard → R2 → bucket → browse to `backups/<today's date>/` and confirm the
   `.dump` file exists with a plausible byte size (cross-check against
   `summary["dump_bytes"]` logged/emailed by the run). Alternatively, if the AWS
   CLI is configured with the same R2 credentials, `aws s3 ls
   s3://<bucket>/backups/<date>/ --endpoint-url
   https://<account-id>.r2.cloudflarestorage.com`.
6. **Confirm the success email**: verify the run-summary email actually arrived
   at every address in `BACKUP_NOTIFY_EMAILS`, with status `OK`, a plausible
   `dump_bytes`/duration, and the correct R2 key.
7. **Force the failure path** to confirm the failure email actually works —
   do this deliberately, once, before relying on cron: temporarily set
   `DATABASE_URL` to an unreachable host (or revoke/mistype the R2 secret) on
   the Railway service's variables, trigger another `railway run --service
   backup python backup.py`, confirm: the run exits non-zero, the log shows
   the error at ERROR level with correct class/message (and full stack only if
   `BACKUP_LOG_LEVEL=debug`), and a **FAILED**-status email actually arrives
   (this is the one email policy that must fire even if
   `BACKUP_NOTIFY_ON=failure` is also being tested — confirm both notify
   settings independently). Then restore the correct variable values.
8. **Confirm restart policy behavior**: after step 7's forced failure, check the
   Railway dashboard's deployment history for that run — it should show as
   failed and Railway should **not** have auto-retried it (verifying
   `restartPolicyType: NEVER` took effect).
9. **Only after 1–8 all pass**: leave `cronSchedule` in place (it was already
   set in step 4's deploy) and let the next scheduled UTC trigger fire
   unattended as the real first automated run. Watch that first automated run's
   logs and confirm the email arrives without any manual `railway run` trigger
   — this is the actual go-live confirmation, distinct from every manual test
   before it.

---

## 7. Known Risks / Limitations (carried over from research, not fully resolved by this plan)

- **Cron skip-not-queue behavior (verified fact #9)**: if a previous scheduled
  run is still executing when the next day's 09:00 UTC trigger arrives, Railway
  **skips** the new invocation outright — it does not queue it and does not run
  both concurrently. A hung `pg_dump` or hung R2 upload therefore silently
  costs a missed day with no automatic catch-up, and there is no built-in
  alert for "the run never even started." Mitigated but not eliminated by
  `BACKUP_PGDUMP_TIMEOUT_MS` / `BACKUP_UPLOAD_TIMEOUT_MS` (Section 3) forcing a
  hang to fail fast and free up tomorrow's slot — but a skipped run still
  produces no failure email (there is nothing running to send one), so a
  missed day would only surface as a gap when someone checks the R2 bucket or
  notices no email arrived. Worth a manual periodic spot-check until/unless a
  separate "did today's backup happen" watchdog is built (explicitly out of
  scope for this plan).
- **Local disk sizing for the temp-file approach (v1 trade-off, deliberately
  accepted)**: `pg_dump` writes its full output to `BACKUP_TMP_DIR` before
  upload begins, so the container needs local disk headroom at least as large
  as the (compressed, custom-format) dump. Railway's default ephemeral
  container disk should comfortably hold a typical school-district database
  dump, but this has **not been measured against the actual production
  database size** — confirm the real dump size on the first manual run
  (Section 6, step 4) before trusting this unattended. If the dump ever grows
  close to the container's disk limit, switch `lib/pg_dump.py` /
  `lib/r2_upload.py` to the streaming design instead: pipe `pg_dump`'s stdout
  directly into a `boto3` multipart upload as the request body (via
  `s3.upload_fileobj()` on the subprocess's stdout pipe), eliminating the disk
  requirement entirely. That trade-off cuts the other way, though: without a
  local copy, a failure partway through can't resume from a partial file —
  `pg_dump` must restart from zero — and a mid-stream failure can leave a
  partial multipart upload in R2 that needs an abort call or a lifecycle rule
  to clean up. Treat streaming as the documented upgrade path, not the
  default, until disk size is shown to be a real constraint.
- **`pg_dump` client/server major-version compatibility (verified fact #2, NOT
  re-confirmed in the latest research pass)**: the Dockerfile's
  `postgresql-client-<MAJOR>` pin must match whatever Postgres major version the
  actual Supabase project is running *at implementation time* — Supabase
  upgrades this over time, and it is **not safe to assume** the version
  documented today still holds when this is built. Verify against
  `supabase.com/docs/guides/platform/backups` and the specific project's
  dashboard (Project Settings → Database shows the running Postgres version)
  before finalizing the Dockerfile's `ARG`. Needs periodic re-verification
  after any Supabase-side Postgres upgrade, since a mismatched client can fail
  the dump outright or silently produce a dump `pg_restore` can't read back.
- **Recommended `pg_dump` flags (verified fact #3, also NOT re-confirmed in the
  latest pass)**: `-Fc --no-owner --no-privileges` is the plan's working
  assumption for a portable, cross-environment-restorable dump, but this
  should be re-confirmed at implementation time against current Supabase
  guidance rather than trusted as settled.
- **IPv6-only direct connection trap (verified fact #1)**: it must be the
  Supavisor **session-mode** pooler connection string, not the direct
  `db.<ref>.supabase.co` host (IPv6-only since Jan 2024, unreachable from
  Railway's IPv4 containers without paying for Supabase's IPv4 add-on) and not
  the transaction-mode pooler on port 6543 (breaks `pg_dump`'s COPY semantics
  under shared backend connections). Easy to get wrong by copying the "wrong"
  connection string out of the Supabase dashboard's several options — worth a
  deliberate double-check during setup, not just trusting whichever string was
  copied first.
- **Resend's 40MB email size cap (verified fact #8)**: the dump is never
  attached to the email by design — the summary is text-only (status, size,
  duration, R2 key). This is a hard constraint, not a preference: a multi-GB
  dump could never fit regardless.
- **No cross-region redundancy**: R2 objects live in one bucket with no
  cross-region replication configured in this plan. If Cloudflare R2 itself
  has an outage or the bucket/account is compromised, the only backup copy is
  gone. Out of scope for this plan but worth flagging as a follow-up (e.g. a
  second lifecycle-ruled prefix in a second provider) if the backup's RPO/RTO
  requirements turn out to need it.
- **No automated restore drill**: this plan produces and stores backups; it
  does not include any automated "restore this dump into a scratch database and
  verify it" step. A backup that has never been test-restored is an unverified
  assumption, not a guarantee. Recommend a periodic (e.g. quarterly) manual
  restore drill as a separate, non-code process — explicitly not part of this
  service's runtime.
- **`boto3` cold-start size**: `boto3`/`botocore` is a heavier dependency than
  the Node plan's `@aws-sdk/client-s3` + `@aws-sdk/lib-storage` pair, but it's
  the standard, well-maintained choice for S3-compatible APIs in Python and
  keeps this service's dependency footprint aligned with what a Python
  implementer would reach for by default — not expected to matter for a
  once-daily one-shot job's cold-start time the way it might for a
  request-serving container.
- **Reference implementations reviewed were Node-based (verified fact #10)**:
  `github.com/railwayapp-templates/postgres-s3-backups` and the one-click
  template at `railway.com/deploy/backup-postgres-to-r2` are both Node.js —
  useful for the `pg_dump` flags and R2-lifecycle edge cases they surface
  (e.g. how they handle partial multipart uploads on failure), but their code
  structure doesn't transfer directly to this Python implementation; treat
  them as a reference for *behavior*, not for *shape* — final code follows
  this repo's `backend`-derived conventions (`lib/logger.py`/`lib/notify.py`
  style, `pydantic-settings` config) instead.
