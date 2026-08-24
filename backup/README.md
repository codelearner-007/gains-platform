# Backup -- Database Backup Service

A one-shot Python script that runs once a day (via Railway's cron trigger),
dumps the production Postgres database with `pg_dump`, uploads the dump to a
Cloudflare R2 bucket under a dated key, and emails a run summary -- success or
failure -- via Resend. Not a server: it runs, dumps, uploads, notifies, and
exits.

## Setup

```bash
cd backup
cp .env.example .env
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

For local development and testing:

```bash
pip install -r requirements-dev.txt
```

`pg_dump` must also be on `PATH` locally, with a client major version
matching the target database's Postgres major version (Supabase Dashboard ->
Project Settings -> Database shows the running version). The Docker image
installs this automatically from the PGDG apt repository -- see `Dockerfile`.

## Running it

```bash
# validate config/connectivity only -- no dump, no upload
python backup.py --dry-run

# the real thing
python backup.py
```

Exit codes: `0` clean (dump + upload succeeded, or `--dry-run` preflight
passed) -- `1` the dump or upload failed, or another caught error occurred --
`2` bad CLI usage (unrecognized flag).

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | Postgres connection string (Supavisor session-mode pooler) | Required |
| `R2_ACCOUNT_ID` | Cloudflare account ID | Required |
| `R2_ACCESS_KEY_ID` | R2 API token access key ID | Required |
| `R2_SECRET_ACCESS_KEY` | R2 API token secret | Required |
| `R2_BUCKET` | Target R2 bucket name | Required |
| `R2_BACKUP_PREFIX` | Key prefix backups are written under | `backups/` |
| `BACKUP_RETENTION_COUNT` | How many most-recent backups to keep in R2, enforced by the app after every successful run (0 is treated as 1) | `3` |
| `BACKUP_PGDUMP_TIMEOUT_MS` | Hard wall-clock limit on the `pg_dump` step (ms) | `1800000` |
| `BACKUP_UPLOAD_TIMEOUT_MS` | Hard wall-clock limit on the R2 upload step (ms) | `1200000` |
| `BACKUP_TMP_DIR` | Local scratch directory for the dump file before upload | OS temp dir |
| `BACKUP_LOG_LEVEL` | `debug` \| `info` \| `warning` \| `error` | `info` |
| `BACKUP_NOTIFY_EMAILS` | Recipients for the run-summary email, comma/semicolon/whitespace separated. Empty disables email | (none) |
| `RESEND_API_KEY` | Resend API key. Required once `BACKUP_NOTIFY_EMAILS` is set | -- |
| `BACKUP_NOTIFY_FROM` | Verified Resend sender address. Required once `BACKUP_NOTIFY_EMAILS` is set | -- |
| `BACKUP_NOTIFY_ON` | `always` \| `failure` (suppresses OK runs; FATAL/FAILED always send) | `always` |

## Code Quality

```bash
# Lint
ruff check lib/ backup.py

# Format
black lib/ backup.py

# Type check
mypy lib/ backup.py

# Tests
pytest
```

## Deployment

See `DEPLOY.md` for the Railway service setup, cron schedule, and the
"start command is deliberately inert" warning -- read that before touching
`railway.json`.
