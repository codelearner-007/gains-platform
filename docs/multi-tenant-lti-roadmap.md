# Multi-Tenant + LTI Roadmap

> Goal: turn the GAINS platform into a production-grade, dynamic, admin-controlled
> **multi-tenant** application where each school (tenant) sees only its own data,
> admins see everything, and the platform can be **launched from Schoology via
> LTI 1.3** exactly like the legacy EdvanceLearning GAINS program.
>
> Status legend: ✅ done · 🟡 in progress · ⬜ todo

---

## Source of truth — what the legacy program does (researched)

The legacy app (`gains legacy/EdvanceLearning`, ABP .NET 8) establishes the behaviours
we replicate:

1. **LTI 1.3 / Advantage** (not 1.1). OIDC third-party login → id_token form-POST →
   JWKS signature validation → nonce/state replay protection → IMS role-URI → app-role
   mapping → tenant resolved from the launch → session → report surface.
2. **Multi-tenancy** = ABP shared-DB with `TenantId` row discriminator; one tenant per
   school; host/superadmin bypasses the tenant filter to see all.
3. **Report visibility**: admin = all; teacher = own students; student = own. Enforced at
   the API (tenant+role filter) and again in the report layer (RLS).

We reproduce 1–3 on **Supabase RLS + FastAPI + Next.js**, rendering reports natively
(no Power BI embed).

---

## Current state (researched)

- **Data plane — DONE & tested.** `schools` tenant root; every raw/dim/fact/cube table
  carries `school_id UUID` FK; RLS policies isolate on the `app.current_school_id` GUC;
  `backend/app/middleware/rls.py` sets it per request; `dim_standard`/`dim_strand` global.
- **Control plane — 3 linked gaps:**
  - No `user_schools` membership table (`auth.users` ↔ `schools` unlinked).
  - JWT claims hook injects role/permissions but **not** school membership.
  - `rls.py` school resolution is a stub → every non-super-admin silently maps to Athenian.
- **Admin UI** has no schools module and no cross-tenant switcher.
- **LTI** — none. Greenfield.
- **Data** — only Athenian, with a small cube slice loaded locally.

---

## Phases

### Phase 1 — Multi-tenant control plane ✅
The load-bearing gap. Make tenant isolation *real per authenticated user*.
- `user_schools` membership table (`user_id`, `school_id`, `school_role`, `is_primary`).
- JWT claims hook injects `school_ids[]` + `is_super_admin`.
- `CurrentUser` carries `school_ids`; replace the Athenian fallback in `rls.py` with
  **claim-driven** resolution: super_admin → `?school_id` override (or all); member →
  their school(s), 403 on foreign school_id.
- Membership management endpoints + RBAC.
- Tests: per-user RLS isolation (member sees only theirs; admin can scope to any).

### Phase 2 — Seed 20–30 tenant schools with data ✅
- Cube fan-out seeder: read backup parquet, synthesize 20–30 schools with varied
  subject/grade **profiles** (elementary / middle / high), sample assessments per school,
  re-key `school_id` + re-hash `id` PKs (collision-free).
- Derive `dim_item`/`dim_section`/`dim_subject`/`dim_question_data` from cubes.
- Create one teacher + one student demo user per school (membership-scoped).
- Verify reports render per school and isolation holds.

### Phase 3 — Admin school management + switcher UI ✅
- Admin `schools` module: list / create / edit / activate.
- Admin school-switcher that threads `school_id` into report requests.
- Member users: no switcher; locked to their school.

### Phase 4 — LTI 1.3 tool provider ✅
- Tables: `lti_registration`, `lti_deployment`, `lti_launch_session` (state/nonce).
- Tool RSA keypair + `/.well-known/jwks.json`.
- `/lti/login` (OIDC init) and `/lti/launch` (validate id_token, map roles, resolve
  tenant from deployment, upsert user, mint session, redirect to report).
- Mock platform harness for local end-to-end (real Schoology org deferred).
- Tests: launch validation, replay rejection, role/tenant mapping.

### Phase 5 — Browser verification (Playwright MCP) ✅
- Multi-tenant isolation: member A cannot see school B's data; admin can switch.
- Schools admin CRUD.
- Reports per school render.
- LTI launch via mock platform → lands authenticated in a school-scoped report.

---

## Non-goals / deferred
- Real Schoology org registration (needs admin developer account) — stubbed + mock-tested.
- `fact_student_submission` full re-derivation — only full YTD needs it; deferred.
- LTI Advantage NRPS/AGS (roster/grade sync) — designed, not built in this pass.
- Power BI embed — replaced by native reports.

---

## Running the demo vs. running the test suite (IMPORTANT)

The seeded demo data and the backend test suite are **mutually exclusive on the
shared local DB**. The transformations tests assert table-global invariants on
the cube/dim tables (`count(dim_item) == distinct staging items`, cube
idempotency, etc.). The synthetic seed rows live in those same tables, so with
demo data present those ~30 transformations/RLS tests fail on inflated counts —
this is data coexistence, **not** a code regression. On a synth-free DB every
test that exercises this work passes.

- **To run the full suite:** clear synthetic data first —
  `DELETE FROM schools WHERE schoology_building_id LIKE 'synth-%';` (FK cascade
  clears its cube/dim rows), then `cd backend && ./venv/bin/python -m pytest tests/`.
- **To restore the demo afterwards:** re-run the three seeders
  (`seed_synthetic_schools.py --schools 25 --reset`, `seed_demo_users.py`,
  `seed_lti.py seed`).

Pre-existing failures unrelated to this work (fail on `main` too): the
permission-message assertions in `test_permissions.py` /
`test_rbac_endpoints_permissions.py` (error text is intentionally redacted to
"Insufficient permissions") and the data-dependent `test_reports_sdd` case.

## Demo credentials (local)
Password for all demo users: `GainsDemo123!`
- `super.admin@gains.demo` — super_admin, sees the switcher with all 26 schools.
- `teacher.oakwood@gains.demo` / `student.oakwood@gains.demo` — Oakwood Middle.
- `admin.riverside@gains.demo` — Riverside Elementary.
- `teacher.lincoln@gains.demo` — Lincoln Elementary.

LTI mock launch (proves the Schoology-style flow):
`backend/venv/bin/python supabase/seeds/seed_lti.py launch --role teacher`
