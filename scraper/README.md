# Schoology Assessment Exporter

Node.js + Playwright scraper for the Gains Platform. It discovers eligible
Schoology assessments via the Schoology REST API, drives the Schoology web UI to
export the 3 result CSVs per assessment, uploads them to **Supabase Storage**, and
then notifies the backend to run ingestion.

This is a port of the legacy Power Automate Desktop bot, retargeted from Azure
Blob to Supabase Storage and driven by backend config instead of `schools.json`.

## Setup

```bash
npm install
npx playwright install chromium      # not needed if using the Docker image
cp .env.example .env
```

Fill in `.env`:

| Variable | Purpose |
|----------|---------|
| `SCHOOLOGY_URL` | Schoology base URL (default `https://app.schoology.com`) |
| `SCHOOLOGY_CREDENTIALS` | Per-school credential map (JSON). Preferred source — see below |
| `SCHOOLOGY_USERNAME` / `SCHOOLOGY_PASSWORD` | Legacy single-identity login (fallback) |
| `SCHOOLOGY_CONSUMER_KEY` / `SCHOOLOGY_CONSUMER_SECRET` | Legacy OAuth 1.0a keys (fallback) |
| `SUPABASE_URL` / `SUPABASE_SERVICE_KEY` | Supabase Storage target (service-role key) |
| `BACKEND_BASE_URL` | Gains backend base URL (e.g. `http://127.0.0.1:8000`) |
| `INGESTION_TRIGGER_SECRET` | Shared machine secret for the ingestion endpoints |
| `SCRAPER_CONCURRENCY` | Optional parallelism across schools (default `2`, hard cap `4`) |
| `DOWNLOAD_DIR` | Optional local download dir override (default `./downloads`) |

School configuration (building IDs, category regex, session, etc.) is fetched
from the backend at startup — there is no local `schools.json`.

## Per-school credentials

Secrets live **only** in this scraper's environment — never in the database, the
repo, or any backend response. `SCHOOLOGY_CREDENTIALS` is a JSON object keyed by
credential *ref*:

```json
{
  "Athenian": { "username": "…", "password": "…", "consumer_key": "…", "consumer_secret": "…" },
  "default":  { "username": "…", "password": "…", "consumer_key": "…", "consumer_secret": "…" }
}
```

Each school resolves its credentials in this order:

1. `SCHOOLOGY_CREDENTIALS[credential_ref]` — the school's `credential_ref` from
   `scraper-config` (a non-secret DB pointer, contract v1.1, optional).
2. `SCHOOLOGY_CREDENTIALS[short_name]` — when `credential_ref` is absent.
3. `SCHOOLOGY_CREDENTIALS["default"]` — shared fallback identity.
4. The legacy flat `SCHOOLOGY_USERNAME` / `SCHOOLOGY_PASSWORD` /
   `SCHOOLOGY_CONSUMER_KEY` / `SCHOOLOGY_CONSUMER_SECRET` vars.

If none match, that school **fails loudly** (a `credential`-class error, no
retry) instead of silently exporting zero assessments. A Schoology API 401 or a
rejected browser login is likewise a fatal `credential` error for that school.

### Onboarding a new school

1. Add the school row in the backend (sets `short_name`, building id, regex,
   session, etc.). Optionally set its `credential_ref`.
2. Add one entry to `SCHOOLOGY_CREDENTIALS` keyed by that `credential_ref` (or by
   `short_name` if no ref), or rely on the `"default"` entry.
3. No code change — the scraper picks the school up from `scraper-config`.

## Concurrency & failure isolation

Schools are processed through a bounded pool sized by `SCRAPER_CONCURRENCY`
(default `2`, hard cap `4`). Each school owns its own browser and credentials, so
they never cross-contaminate. One school failing never aborts the batch — every
school reports an outcome in the final summary. Transient failures (nav timeout,
transfer wait, upload error) get one retry with a 30 s backoff; credential
rejections do not retry. If **any** school fails, the process exits non-zero.

The `scraper-complete` POST is retried up to 3 times with exponential backoff and
honors `429` `Retry-After`.

## Run

```bash
node schoology-exporter.js --dry-run              # discovery only, no browser/upload
node schoology-exporter.js                        # full run (all active schools)
node schoology-exporter.js --school "Athenian"    # single school (partial name match)
node schoology-exporter.js --headed               # visible browser for debugging
```

## Backend contract

- `GET /api/v1/ingestion/scraper-config` → `{ storage: { bucket }, schools: [...] }`
  (active schools only; no credentials in the payload). Each school may carry an
  optional `credential_ref` (contract v1.1, additive — absent-tolerant).
- `POST /api/v1/ingestion/scraper-complete` `{ short_name, note? }` → `202` with the
  created run id. Fired once per school after its uploads finish.

Both calls send `X-Ingestion-Secret: <INGESTION_TRIGGER_SECRET>`. A failed
`scraper-complete` (after 3 retries) marks that school failed; any failed school
exits the process non-zero.

## Storage key convention (frozen)

Each CSV is uploaded to:

```
<short_name>/<session>/<category>/<subject>/<grade>/<section>/<original-Schoology-filename>.csv
```

- The **original** Schoology filename is preserved (keeps the
  `Question-Data-` / `Submission-Summary-` / `Student-Submissions-` prefixes the
  backend classifier keys on). The local `<sectionId>_<grade>_` rename is dev-only
  and never used for the storage key.
- The two-space `1 - Lesson  Assessments` category literal is preserved verbatim.
- No `%20` encoding — the Supabase client handles it.

The backend archives ingested files under `processed/<short_name>/<run_id>/…`, so
`processed/` is reserved and no school `short_name` may be `processed`.

## Output per assessment

- `Submission-Summary-{name}-{timestamp}.csv` — per-student scores + per-question points
- `Student-Submissions-{name}-{timestamp}.csv` — every answer for every question
- `Question-Data-{name}-{timestamp}.csv` — question text, correct answers, stats

## Docker

```bash
docker build -t schoology-exporter .
docker run --rm --env-file .env schoology-exporter --dry-run
```

Secrets are supplied at runtime via `--env-file` / environment variables; nothing
is baked into the image.
