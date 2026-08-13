# GAINS Platform — Project Overview

A plain-language map of what this codebase is, what it already does, and what
can be built on top of it.

> **Note:** the root `README.md` is a stale leftover from the SaaS starter
> template this project was forked from. It describes generic auth/RBAC and has
> nothing to do with the education product. The authoritative docs are
> `CLAUDE.md` (Part 2) and `docs/`.

---

## 1. What It Is

Schools give tests in **Schoology** → a bot downloads the results every night →
a data warehouse crunches them → **11 report pages** show teachers *which skills
students are failing*.

It is a rebuild of a legacy **Azure Synapse + PySpark + Power BI** stack onto
Next.js + FastAPI + Supabase. The decompiled Power BI file in
`data/_pbix_extract/` is the parity spec — new reports are checked against the
old numbers.

**Tech stack**

| Layer | Technology |
|---|---|
| Frontend | Next.js 16 (App Router), React 19, TanStack Query, Tailwind v4, shadcn/ui |
| Backend | FastAPI, SQLAlchemy 2.0 async (asyncpg), Pydantic v2, slowapi |
| Database | Supabase PostgreSQL, Row-Level Security, UUID v7 |
| Scraper | Node.js + Playwright |

**Data flow**

| Step | What happens | Where |
|---|---|---|
| 1. Grab | Bot logs into Schoology, downloads 3 CSVs per test | `scraper/` |
| 2. Store | Files uploaded to Supabase Storage | `scraper/schoology-exporter.js` |
| 3. Parse | CSVs → clean typed rows | `backend/app/jobs/parsers/` |
| 4. Stage | Raw → typed tables, tenant overrides applied | `01_staging/` |
| 5. Dimensions | Lookup tables (student, teacher, standard…) | `02_dimensions_a` → `06_dimensions_e` |
| 6. Facts | One row per student-per-question answer | `07_facts/` |
| 7. Hash | Pseudonymised twins for privacy-safe sharing | `08_hash/` |
| 8. Cubes | Pre-computed summaries (fast reports) | `09_cubes/` |
| 9. Show | FastAPI serves it, Next.js renders it | `backend/app/api/v1/reports/` |

---

## 2. Who Uses It

Two independent role systems:

| System | Values | Purpose |
|---|---|---|
| Platform RBAC | `super_admin`, `user`, custom roles | Can you touch the admin panel? |
| School role (`user_schools`) | `admin`, `teacher`, `student`, `member` | What can you see in this school? |

**Teachers are the primary audience.** Students appear as *data rows*, not
readers. Admins get school-wide views plus ingestion control.

Multi-tenant: every warehouse table carries `school_id` with RLS. Users arrive
either by normal login **or by LTI 1.3 launch from inside Schoology/Canvas**.

---

## 3. Pages That Already Exist

### Public

| Route | What it is |
|---|---|
| `/` | Landing page (invitation-only product), CTA flips when signed in |
| `/privacy`, `/terms` | **Still placeholder template text** |
| `/forbidden` | Branded 403 with a back link |

### Auth

| Route | What it is |
|---|---|
| `/auth/login` | Password + magic link + Google, all in one card |
| `/auth/2fa` | TOTP challenge (auto-skips if already verified) |
| `/auth/confirm` | Anti-scanner interstitial — email token never reaches the page |
| `/auth/accept-invite` | Invitee sets their password |
| `/auth/forgot-password`, `/auth/reset-password` | Password recovery |

### App

| Route | What it is |
|---|---|
| `/app` | **Main dashboard** — KPI hero + sparkline, subject cards, grade chips, filter popover, and 3 switchable infinite-scroll tables: By Assessment / By Strand / By Student |
| `/app/user-settings` | Profile, password, MFA (QR enroll), timezone, theme, active sessions |
| `/app/students/[uid]/report` | One student's printable report card (A4 portrait) |

### Admin

| Route | What it is | Permission |
|---|---|---|
| `/admin` | Overview — stats, pending invites, role spread, ingestion health | any admin-entry perm |
| `/admin/rbac` | **Drag-and-drop role ladder** + permission switch matrix | `roles:read` / `permissions:read` |
| `/admin/users` | Roster, bulk ban/unban/delete/invite, school access | `users:read_all` |
| `/admin/audit` | Searchable log, plain-English text, CSV download | `audit:read` |
| `/admin/schools` | Tenant CRUD, logo upload, LTI binding | `schools:read_all` |

---

## 4. The 11 Reports

Single source of truth: `frontend/src/lib/reports/report-types.ts`.

### Assessment family — about ONE test (needs `?item_id`)

| Report | What it shows | Kind |
|---|---|---|
| Question Response Analysis | **Flagship** — KPI strip, per-question table, strand + standard rollups, multi-select cross-filtering | Interactive |
| Standards Deep Dive | Strand treemap, ranked bars, performance-band bars, "open in QRA" jumps | Interactive |
| Question Summary | Student × question score matrix — 4 variants (base / teacher / redacted / header-highlights) | Print |
| QRA (Print) | Printable per-question rendering | Print |
| QRA By Teacher | Per-question results grouped by teacher | Print |
| QRA By Standard + Teacher | Grouped by standard, then teacher | Print |
| Incorrect Answer Details | One question: who picked which wrong answer (needs `?question_id`) | Drill-down |

### Program family — about the WHOLE YEAR

| Report | What it shows | Kind |
|---|---|---|
| Year To Date | Student × standard longitudinal matrix, 3 column variants. Requires subject + grade | Interactive |
| Standard Summary | One card per standard (parity-trimmed to legacy PBIX page 14) | Print |
| Strand Summary | One card per strand + within-strand column chart | Print |
| Forward View | **Most actionable** — weak standards by period → unit, adjustable flag threshold | Interactive |

Every report has a matching `/export.xlsx` route that reuses the **same**
service method as the JSON endpoint, so exports can never drift from screen.
PDF is `window.print()` against a print stylesheet (A4 landscape default).

---

## 5. Data Available

| Layer | Contents |
|---|---|
| **Rosters** | students, teachers, **parents** (with children's UIDs), courses, sections |
| **Content** | every assessment (`dim_item`), every question with correct answer + standards alignment (`dim_question_data`) |
| **Standards** | **7,958 standards** (`dim_standard`) + **7,071 strand mappings** (`dim_strand`), with CPALMS/Florida codes |
| **The fact** | `fact_student_submission` — one row per *student × question × position × answer × standard*, with points earned/possible |
| **Cubes** | 8 pre-aggregated rollups (below) |
| **Privacy** | `*_hash` twin tables for pseudonymised sharing |

### The 8 cubes

| Cube | Answers |
|---|---|
| `cube_school_summary` | "How did the whole school do on this test?" |
| `cube_grade_summary` | "…and per subject, with best/worst?" |
| `cube_question_summary` | "How did each question go?" + wrong-answer text |
| `cube_question_summary_overall` | **The canonical grade average** used by all KPIs |
| `cube_question_summary_overall_by_item` | Same, per-item — local verification artifact, dropped on prod |
| `cube_questionincorrectchoice_summary` | "How many picked each wrong option?" |
| `cube_standard_summary` | "How did the class do on this standard?" |
| `cube_user_summary` | Widest — powers the YTD matrix and section dropdown |

### Config tables — the "messy real world" layer

| Table | Fixes what |
|---|---|
| `item_label_overrides` | Tests filed under the wrong subject/grade in Schoology |
| `subject_grade_overrides`, `teacher_pair_overrides` | Messy Schoology folder names → clean labels |
| `student_exclusions` | Staff/demo accounts inflating headcounts |
| `fact_row_exclusions` | Duplicate re-exported rows |
| `locked_sessions` | Freezes a finished school year — DB triggers refuse DELETE/TRUNCATE |

---

## 6. Backend API Surface

All routes are `/api/v1/*` (Next.js rewrites to FastAPI — no CORS).

| Group | What's there |
|---|---|
| `/auth`, `/profile`, `/sessions` | Identity, profile, avatar, active sessions |
| `/roles`, `/permissions`, `/users`, `/audit` | RBAC + user management + audit trail |
| `/dim/*` | **8 lookup routes** — standards, strands, subjects, grades, sections, sessions, assessment-types, instructors |
| `/assessments/*` | Paginated grid, meta, summary, questions, standards, wrong answers |
| `/students/*` | Paginated roster with mastery bands, per-student report |
| `/reports/*` | 11 JSON reports + 11 matching XLSX exports + dashboard aggregates + data-quality audit |
| `/schools/accessible` | Tenant switcher data |
| `/admin/*` | Schools CRUD, ingestion runs + trigger, LTI binding |
| `/ingestion/*` | Machine-auth scraper config + completion webhook |
| `/lti/*` | LTI 1.3 OIDC login, launch, ticket consume, JWKS |

---

## 7. Reusable Building Blocks

| Asset | Detail |
|---|---|
| `components/app/modules/reports/shared/` | **~30 components** — `ReportCanvas`, `AssessmentReportShell`, headers, breadcrumbs, family tabs, sub-tabs, `ReportSlicer` + `ActiveFilterBar`, `ExportMenu`, `ReportScopePrompt`, `AlignmentEmptyState`, `KpiCard`/`KpiStrip`, `ChartContainer`, `RankedBarList`, loading/error states |
| `/dim/*` endpoints | Every filter dropdown already exists |
| URL-as-state | No Redux/Zustand — the URL *is* the state, so every filtered view is a shareable link |
| `useReportFilters()` | Multi-select strand / standard / instructor slicers |
| `useSummaryFilters()` | Program-report filter bar (session, subject, grade, category, section) |
| `SelectedSchoolContext` | Reconciles `?school_id`, localStorage, and accessible-schools |
| `lib/reports/colors.ts` | Frozen performance ramp — do not redefine |

**Performance colours:** 🔴 under 70% · 🟡 70–80% · 🟢 80%+

---

## 8. Rules You MUST Follow

| Rule | Why |
|---|---|
| One test given to N sections = **ONE report** | Merged on the section-agnostic `subject_id`; nearly every cube query assumes it |
| Always use `get_db_with_rls` for tenant reads | It runs `SET LOCAL ROLE authenticated` first, dropping superuser bypass. No query has a manual `WHERE school_id` |
| Per-student numbers come from **the fact, not cubes** | `student_repository` uses `DISTINCT ON` to collapse standard-alias fan-out |
| **LTI paths are an allowlist** | Only `/app`, `/app/reports/*`, `/app/students/*`. **Any new `/app/*` route is blocked by default** |
| Role hierarchy: **lower = more senior** | `super_admin` = 0, `user` = 100,000, no role = 2147483647 (fail-closed) |
| Warehouse tables have **no ORM model** | Only the 7 RBAC/identity tables are SQLAlchemy; everything else is raw SQL |
| Next.js = auth only, FastAPI = all database | Never import the Supabase client in components/hooks/services |
| UUID v7 for all primary keys | `uuid_generate_v7()`, never v4 |

---

## 9. Security Already Handled

| Layer | What's built |
|---|---|
| JWT | JWKS verification (ES256/RS256) with key-rotation retry; never blind-decodes |
| Tenancy | RLS via the `app.current_school_id` GUC; a wrong `?school_id=` returns **403, not a silent downgrade** |
| Rate limits | slowapi, bucketed per **authenticated user id** (not IP), so one school behind a NAT isn't one bucket |
| CSRF | `enforceSameOrigin` on all Next.js mutation routes |
| MFA | TOTP, **fails closed** — errors redirect to login, never let through |
| Machine auth | Two shared secrets, constant-time compare, **fail closed when unconfigured** |
| Superadmin protection | Live `auth.admin.getUserById()` check; stale `app_metadata` never trusted |
| Email links | Token moved to an httpOnly cookie before the interstitial — scanners can't burn it |
| Data guards | `validate_no_cross_band.sql` fails the build if a test maps to two grades |
| Audit trail | Service-role-only inserts; authenticated users cannot forge entries |

---

## 10. Ingestion Is Production-Grade

Not fire-and-forget background tasks — a **durable queue**:

- `ingestion_runs` table with `FOR UPDATE SKIP LOCKED` claim
- Lease + heartbeat + reaper (requeues runs orphaned by a crash or redeploy)
- SIGTERM-aware stop, per-file SAVEPOINT so one bad file can't kill a run
- SHA-256 file dedupe via `ingested_files`
- Scoped rebuilds (`--scope-run-id`) so only fresh assessments re-transform

**Two data sources:** Schoology (full — scores, questions, answer choices) and
HMH curriculum exports (`hmh_assessed_standards.py`). HMH carries no answer
choices, so distractor/IAD reports degrade to empty states **by design**, while
all score/standard/mastery reports populate fully.

---

## 11. Best Candidates For New Pages

Data and APIs already exist — only the screens are missing.

| Idea | Why it's ready | Effort |
|---|---|---|
| **Teacher home** | `dim_teacher` + per-teacher cube variants + `/dim/instructors` all exist | 🟢 Low |
| **Section / class view** | `dim_section` has rosters and instructors, no page reads it | 🟢 Low |
| **Ingestion monitor UI** | Heartbeat/lease columns + `/admin/ingestion/runs` were built *for* a live status screen | 🟢 Low |
| **Parent portal** | `dim_parent` is populated with children's UIDs, zero pages read it | 🟡 Medium |
| **HMH mastery-only report** | A variant that hides answer-analysis panels instead of showing empty states | 🟡 Medium |
| **Standards mastery over time** | `cube_user_summary` already pre-rolls by year and standard | 🟡 Medium |
| **Real legal pages** | Privacy/Terms are still placeholder template copy | ⚪ Trivial |

Remember: any new `/app/*` route must be added to the LTI allowlist if
Schoology-embedded users should see it.

---

## 12. Known Issue

`docs/audit/06_cubes_and_reports.md` documents a **live KPI discrepancy** versus
the legacy Power BI report (Grade Average 66.9% → 65.4%). Two causes:

1. `get_canonical_kpis_for_item` averages *per-student, then per-question*
   instead of a straight `SUM(points) / SUM(possible)`.
2. Strand/standard rollups read `cube_question_summary` (per-position,
   per-identifier — which double-counts multi-aligned questions) instead of
   `cube_question_summary_overall`, which is what the legacy DAX consumed.

**The cube columns are correct — the bug is at read time.** Fixable in
Python/SQL without touching any data.

---

## 13. Project Layout

```
frontend/src/
├── app/
│   ├── admin/[module]/      # Admin panel (rbac, users, audit, schools)
│   ├── app/                 # Dashboard, reports, students, settings
│   ├── auth/                # Login, 2FA, invite, recovery
│   └── api/                 # Next.js routes — AUTH ONLY
├── components/
│   ├── admin/modules/       # Admin UI per module
│   ├── app/modules/reports/ # Report UI (shared/ + one dir per report family)
│   └── ui/                  # shadcn/ui primitives
└── lib/
    ├── services/            # API service layer
    ├── reports/             # Report registry, filters, colors, exports
    └── supabase/            # Supabase clients (API routes only)

backend/app/
├── api/v1/                  # FastAPI endpoints
├── services/                # Business logic
├── repositories/            # SQLAlchemy / raw SQL data access
├── models/                  # ORM models (RBAC/identity only)
├── jobs/                    # Ingestion + parsers + CLI
└── transformations/         # SQL pipeline (staging → dims → facts → cubes)

supabase/
├── migrations/              # Schema
└── seeds/                   # Roles, standards, school config, data corrections

scraper/                     # Playwright Schoology exporter
data/                        # Source CSVs + decoded PBIX reference
docs/                        # Audit + reference documentation
```

---

## 14. Documentation Index

| Doc | When to read |
|---|---|
| `CLAUDE.md` | Working agreement + business rules — read first |
| `docs/standards-alignment.md` | Where per-question standards come from, what breaks when missing |
| `docs/audit/01_ingestion.md` … `06_cubes_and_reports.md` | One per pipeline layer |
| `docs/audit/hmh_known_issues.md` | HMH ingestion limits and trade-offs |
| `docs/audit/fixes/03_prod_data_sync_runbook.md` | **Canonical procedure for any prod data change** |
| `docs/audit/edvancelearning-ims-integration.md` | How standards were sourced from CASE Network |
