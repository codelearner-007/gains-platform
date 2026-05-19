# 53 — Zero-Gains Runtime Audit

**Date:** 2026-05-08
**Scope:** Full audit of `E:\Work\PS_P\Gains-platform\` for any RUNTIME dependency on the legacy systems we will decommission once cutover completes.
**Verdict:** ZERO BLOCKERS. The platform has no runtime dependency on the legacy `gains/` folder, on `*.edvancelearning.us`, on `casenetwork.1edtech.org`, or on `api.schoology.com`.

---

## §1 Methodology

### Searches executed (whole-repo, ripgrep / Grep tool)

| Pattern | Purpose | Hits in source code |
|---|---|---|
| `gains[/\\]` | Path references to the legacy gains folder | 0 in source; only `tasks/backlog/*.md` and `docs/superpowers/plans/*.md` (plan docs) |
| `edvancelearning\.us` | Edvance LMS / tenant-config / standards mirror APIs | 0 in source; only plan docs |
| `1edtech\.org` | IMS CASE Network upstream | 0 in source; only plan docs |
| `schoology\.com` | Schoology REST API | 0 in source; only plan docs |
| `tenant-config|case-network|local-standards` | Endpoint path fragments | 0 anywhere |
| `lib/pilot|lib\\pilot` | Frontend pilot static dataset | 0 imports; 4 stale comments (see §3) |
| `data/_pilot|data\\_pilot` | Static pilot dataset directory | 0 imports; only docstring/comment refs (see §3) |
| `data/Athenian|data\\Athenian` | Real CSV corpus | Only `LocalBlobClient` (Phase 1 dev mode) and tests |
| `data/_pbix_extract|data\\_pbix_extract` | PBIX evidence specs | Only docstrings citing line-numbered specs |
| `186370968` / `7448280461` | Hardcoded Athenian / Brightview building IDs | Only seed SQL (`schools_athenian.sql`, `teacher_pair_overrides.sql`), tests, and `middleware/rls.py:ATHENIAN_BUILDING_ID` constant |
| `requests\.get|httpx\.|fetch\(|aiohttp|urllib` | All outbound HTTP in backend | One match: `core/security.py` → Supabase JWKS (auth, not legacy) |
| `E:[\\\/]Work[\\\/]PS_P[\\\/]gains` | Hardcoded absolute paths to legacy folder | 0 in source; only plan docs |
| `localhost:8000|127\.0\.0\.1:8000` | Hardcoded backend URL bypassing rewrite | Only in `.env.example` defaults / `next.config.ts` rewrite target — internal FastAPI, not legacy |

### Directories surveyed

- `frontend/src/**` (app, components, lib, hooks, services)
- `backend/app/**` (api, services, repositories, jobs, transformations, schemas, models, middleware, core)
- `supabase/migrations/**`, `supabase/seeds/**`
- All env example files

### Directories explicitly skipped

- `node_modules/`, `.next/`, `__pycache__/`, `gains/` (frozen legacy), `data/_pbix_extract/` (evidence corpus, not runtime)

---

## §2 Blockers

**NONE.** No runtime dependency on the legacy gains program was found in the platform code.

The deferred Phase 7 cron jobs the audit explicitly listed as candidates — `sync_tenant_config.py`, `sync_standards.py`, `sync_users.py` — **DO NOT EXIST IN THE REPO**. They have not been implemented yet (Phase 7 is deferred). The current `backend/app/jobs/` tree contains only:

```
backend/app/jobs/
  __init__.py
  blob_client.py            # local-fs / azure-blob abstraction (NO HTTP)
  db.py                     # async SQLAlchemy session helper
  file_path_parser.py       # parses CSV file paths
  ingest_schoology.py       # orchestrator: reads CSVs from local FS → raw_* tables
  unique_key.py             # row-key hashing
  parsers/{question_data,student_submission,submission_summary,common}.py
```

`ingest_schoology.py` is named after the upstream domain but **does not call any Schoology API**. It reads CSVs from `data/<School>/...` via `LocalBlobClient` (Phase 1 dev) or `AzureBlobClient` (Phase 7 stub — every method raises `NotImplementedError`). No `requests`, `httpx`, `aiohttp`, or `urllib` HTTP call is made anywhere in the jobs tree.

---

## §3 Acceptable references (🟡)

### 3.1 — Domain identifier columns / values (NOT API calls)

| Location | Reference | Why acceptable |
|---|---|---|
| `supabase/migrations/20260507000020_tenants.sql` | `edvance_tenant_id TEXT`, `source TEXT DEFAULT 'edvance_api'` | Column / value — stored data, no HTTP. Once cutover, just legacy-source labelling. |
| `backend/app/repositories/school_repository.py` | `schoology_building_id`, `edvance_tenant_id` columns in SELECT/INSERT | Column names only. |
| `backend/app/schemas/admin.py` | `edvance_tenant_id: Optional[str]` | Pydantic field name. |
| `supabase/seeds/schools_athenian.sql` | `'186370968'` (Athenian building id) | Seed data — checked in once, loaded at deploy. |
| `supabase/seeds/teacher_pair_overrides.sql` | `'186370968'`, `'7448280461'` | Seed data. |
| `backend/app/middleware/rls.py:45` | `ATHENIAN_BUILDING_ID = "186370968"` | RLS context constant for current tenant; will be table-driven post-cutover but no external dependency. |
| `backend/app/jobs/ingest_schoology.py:21` | `python -m ... --school 186370968` | Docstring CLI example. |
| `backend/tests/**` (multiple) | `'186370968'` in fixtures / queries | Tests; no runtime impact. |

### 3.2 — Stale `lib/pilot` / `data/_pilot` references in DOCSTRINGS (cosmetic only)

These are leftover docstring/comment references after Phase 6 renamed `frontend/src/lib/pilot/` → `frontend/src/lib/reports/`. They are **comments only** — no imports, no I/O, no behaviour. Recommend a cosmetic comment-update PR.

| File | Line | Content |
|---|---|---|
| `backend/app/schemas/reports.py` | 3 | `These shapes are the contract that frontend/src/lib/pilot/dataset.ts consumes.` |
| `backend/app/services/report_service.py` | 4 | `The shapes returned here MUST match frontend/src/lib/pilot/dataset.ts so the` |
| `backend/app/jobs/parsers/question_data.py` | 58 | `# This convention matches the pilot script (data/_pilot/_build_pilot.py).` |
| `backend/app/transformations/__init__.py` | 6 | `data/_pbix_extract/40_schoology_py_spec.md` (PBIX evidence spec — fine to keep) |
| `backend/app/transformations/01_staging/stg_standard.sql` | 10 | Same PBIX spec reference (fine). |
| `backend/app/jobs/file_path_parser.py` | 3 | PBIX spec citation (fine). |
| `backend/app/jobs/blob_client.py` | 58 | `as data/<SchoolShortName>/ (e.g. data/Athenian/)` — describes runtime convention; accurate. |
| `backend/app/jobs/ingest_schoology.py` | 497 | Same — accurate. |
| `frontend/src/lib/reports/colors.ts` | 2-3 | Cites PBIX evidence specs as the design source. Comment only. |

### 3.3 — Plan / task / migration documentation references

All these files are documentation, not runtime paths:

- `tasks/backlog/01-gains-pipeline-finalized-plan.md` — full plan, references `E:\Work\PS_P\gains\...` as reading material.
- `tasks/backlog/02-extended-reports.md` — dictates this very audit.
- `docs/superpowers/plans/2026-05-05-gains-pipeline.md` — same plan.
- `supabase/migrations/20260507000050_dim_tables.sql:3` — `-- data/_pbix_extract/40_schoology_py_spec.md` citation in comment.
- `supabase/migrations/20260507000070_cube_tables.sql:215` — same pattern.

### 3.4 — Test fixtures (not runtime)

| File | Status |
|---|---|
| `backend/tests/jobs/test_ingest_athenian.py` | Skips if `data/Athenian/` missing. |
| `backend/tests/transformations/conftest.py` | Skips if `data/Athenian/` missing. |
| `backend/tests/jobs/test_file_path_parser.py:121-127` | Pure-string fixture; no FS access. |
| `backend/tests/transformations/test_full_pipeline.py:57,127` | `pytest.mark.skipif(not ATHENIAN_DIR.exists(), …)` |

These are fixture inputs — they bind to the local on-disk corpus when present, are skipped otherwise. Zero impact on production.

### 3.5 — `LocalBlobClient` default `data_root`

`backend/app/jobs/blob_client.py:136` defaults the local data root to `<repo>/data` when `INGESTION_SOURCE=local`. This is the dev mode that exists so we can run ingestion against checked-in fixtures. Phase 7 swaps to Azure via env var. Acceptable: it's a configurable, no path is hard-coded into request handlers.

### 3.6 — Standards seed loader (`supabase/seeds/load_standards.py`)

- Pure CLI tool (`if __name__ == "__main__"`).
- Reads only its sibling CSVs `dim_standard.csv` and `dim_strand.csv` from `supabase/seeds/`.
- No reach-out to any external API.
- Run at **deploy / setup time**, not on a request path.

### 3.7 — `frontend/public/pilot/athenian-logo.png`

Static brand asset only. No legacy code reference.

---

## §4 Clean code paths (🟢)

These categories were inspected and contain ZERO references to legacy gains, edvance, 1edtech, or schoology.com:

- `frontend/src/app/**` (pages, layouts, route handlers)
- `frontend/src/components/**`
- `frontend/src/hooks/**`
- `frontend/src/lib/services/**`
- `frontend/src/lib/reports/**` (only PBIX spec citations in `colors.ts` — historical design source, no I/O)
- `backend/app/api/**` (all v1 routers — assessments, reports, dim, admin, auth, dashboard, users, roles, permissions, audit)
- `backend/app/services/**` (all services including the new `report_service`, `assessment_service`, `dim_service`, `school_service`, `ingestion_admin_service`)
- `backend/app/repositories/**` (cube, dim, school, ingestion_run — all use SQLAlchemy against our own DB; no HTTP)
- `backend/app/transformations/**` (pure SQL ports of notebook logic — no external calls)
- `backend/app/middleware/**`
- `backend/app/models/**`
- `backend/app/schemas/**`
- `backend/app/core/**` (only `core/security.py` makes HTTP calls — to Supabase JWKS only)
- `supabase/migrations/**` (no embedded HTTP / no extension references to legacy hosts)

### Backend HTTP egress inventory (single source)

```
backend/app/core/security.py:29   httpx.AsyncClient → settings.SUPABASE_URL/auth/v1/.well-known/jwks.json
```

That is the **only** outbound HTTP call across the entire backend application code. It targets our own Supabase auth, not a legacy system.

### Frontend HTTP egress

The frontend uses Next.js rewrites (`/api/v1/:path*` → FastAPI) and Supabase client (auth only). No fetch / axios / XHR call targets `edvancelearning.us`, `1edtech.org`, or `schoology.com`. `NEXT_PUBLIC_API_URL` (default `http://127.0.0.1:8000`) is the FastAPI backend, not legacy.

### Phase 7 deferred jobs — confirmation

The audit prompt asked us to document these explicitly:

| Expected file | Status |
|---|---|
| `backend/app/jobs/sync_tenant_config.py` | DOES NOT EXIST. Phase 7 deferred. |
| `backend/app/jobs/sync_standards.py` | DOES NOT EXIST. Phase 7 deferred. |
| `backend/app/jobs/sync_users.py` | DOES NOT EXIST. Phase 7 deferred. |

When Phase 7 implements these, they MUST be implemented as fail-soft cron jobs (per plan), with feature flags / try-except wrappers that allow the platform to function with zero impact if the upstreams are decommissioned. They must NOT be invoked on any request path.

---

## §5 Recommended actions

No blockers. Recommendation list is purely cosmetic / preventive:

1. **(Cosmetic, low priority)** Update three stale docstring/comment references from `frontend/src/lib/pilot/...` → `frontend/src/lib/reports/...` so future readers don't chase a dead path:
   - `backend/app/schemas/reports.py:3`
   - `backend/app/services/report_service.py:4`
   - `backend/app/jobs/parsers/question_data.py:58` (rephrase: `# This convention matches the original pilot data-prep script.`)

2. **(Future Phase 7 guardrail)** When `sync_tenant_config.py` / `sync_standards.py` / `sync_users.py` are introduced, gate them behind `INGESTION_SYNC_ENABLED` env flags and wrap network calls in `try/except` that logs and exits 0 on upstream failure — so a decommissioned legacy host never breaks the cron.

3. **(Optional)** Move `ATHENIAN_BUILDING_ID = "186370968"` out of `backend/app/middleware/rls.py` and look it up from the `schools` table at startup (or from an env var), so the value lives only in seed data.

4. **(Optional)** Add a CI lint that fails the build if any file under `frontend/src/`, `backend/app/`, or `supabase/migrations/` matches the regex `(edvancelearning\.us|1edtech\.org|api\.schoology\.com|gains[\\/])` outside a `.md` file or a clearly-marked Phase 7 sync job. Locks in the current zero-blocker state.

---

**Audit verdict:** the Gains-platform application can run with the legacy `E:\Work\PS_P\gains\` folder fully removed and with `*.edvancelearning.us`, `casenetwork.1edtech.org`, and `api.schoology.com` blocked at the network layer. Cutover is unblocked from a dependency-isolation standpoint.
