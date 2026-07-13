# Prod data-sync runbook (reload + surgical), 2026-07-13

**Read this before changing any DATA on the production Supabase DB.** It supersedes
the in-place "convergence" approach in `02_assessment_misfiling_prod_runbook.md`
for whole-DB syncs. Production has **no raw/staging layer** (derived-layer-only
load), so the pipeline can never be re-run on prod — it would wipe everything.
The only safe way to correct prod DATA is to converge it to the verified LOCAL
state, either by full reload (Method A) or a surgical delete + cube-reload
(Method B).

Prod is currently **byte-identical to verified local** (2026-07-13 reload). Keep it
that way: fix LOCAL first (durably, via seeds + pipeline), verify, then propagate.

---

## Environment facts (the ones that bite)

- **Prod connection:** Supavisor pooler only (`aws-1-...pooler.supabase.com:5432`,
  user `postgres.<ref>`). No direct/IPv4. Reach it via
  `railway run --service backend bash -c 'psql "$DATABASE_URL" ...'` (railway
  injects `DATABASE_URL`) or the Supabase MCP `execute_sql` (management API; times
  out on full-table aggregates >~15 s).
- **Pooler drops single long statements** (~24 s+ killed the original 1.26M-row
  UPDATE with a 1.2 GB WAL burst). It tolerates *chained short* statements fine.
  Keep every statement well under ~30 s. The DB itself recovers from WAL bursts
  (stays ACTIVE_HEALTHY; autovacuum then briefly delays the pooler).
- **Backend does NOT migrate on deploy** — start cmd is bare `uvicorn`. So a
  backend deploy touches zero DB state.
- **The ONLY automatic prod-migration path** is CI `.github/workflows/supabase-migrations.yml`:
  it runs `supabase db push` against prod on any **push to `main`** touching
  `supabase/migrations/**` (path-filtered; gated by the `production` GitHub
  Environment). A push touching only `supabase/seeds/**` does NOT trigger it.
- **Railway auto-deploys the backend from `main`** on push (GitHub integration).
- **macOS `/bin/bash` is 3.2** — no associative arrays; put lookups in a manifest file.
- **Rollback:** `pg_dump -Fc -n public` taken *before* any change, restored via
  **pg17 Docker** (`docker run --rm -v <dir>:/b postgres:17 pg_restore ...`) —
  local pg_restore 15 can't read pg17's v1.16 archive format. The prod pre-remediation
  dump is `~/Desktop/PS_P/gains-prod-db-backups/prod_pre_remediation_20260712_233949.dump`.

---

## Method A — full reload (make prod == verified local)

Used 2026-07-13 to apply the entire 2026-07 audit remediation. Steps:

1. **Backup prod** (Docker pg17): `pg_dump "$DATABASE_URL" -Fc -n public -f dump`.
   Validate with `pg_restore --list` (expect ~700 TOC / ~71 TABLE DATA).
2. **Freeze the export from local** — never load from a live local DB that dev
   work might move under you. Row-safe TEXT-format COPY (escapes embedded
   newlines → 1 line = 1 row), explicit column lists, chunked for big tables
   (fact/fact_hash 16×, cube_user 12×, qic 4×) via a `get_byte(md5(ctid))%N`
   bucket. Verify chunk line-sums == certified counts before loading.
3. **Schema diff** local vs prod (`string_agg(attname ORDER BY attnum)` per table)
   — must be identical for COPY-with-explicit-columns. Abort on any diff.
4. **Per-table TRUNCATE + chunked COPY** (only star tables: `fact_student_submission`,
   `fact_student_submissions_hash`, all `dim_*`, all 9 `cube_*`). NEVER touch
   `schools` (tenancy config; every star table FKs to it). Guardrails per COPY:
   `SET statement_timeout='120s'; SET session_replication_role=replica;`
   - `session_replication_role=replica` **skips the per-row FK check to `schools`**
     — that check made wide-row fact COPY exceed 60 s (100k fact chunk: 60s+ → 25s).
     Safe because the data is known-FK-valid (local's school_ids ⊆ prod `schools`).
   - **Heavily-indexed tables (fact: 9 idx, fact_hash: 6):** progressive
     index-maintenance blows later chunks past timeout. Pattern: capture index
     DDL → `DROP INDEX` all → load at constant speed (~15 s/100k) → recreate each
     index one-by-one with `statement_timeout=0` (pooler tolerated the ~3.5 min
     `ytd_dedup_idx` build). The UNIQUE pk-index rebuild doubles as a dup check.
   - Restart-table-on-failure (re-TRUNCATE + replay chunks) so an ambiguous
     COPY-success can't duplicate. Done-markers make the whole run resumable.
5. **`VACUUM (ANALYZE)`** every reloaded table (COPY leaves the visibility map
   unset → aggregates run ~10× slow). `VACUUM` needs its OWN `-c` — it can't share
   a `-c` with `SET` (implicit txn block → "VACUUM cannot run inside a transaction").
6. **Verify:** per-school baseline (rows/students/items/subj/points) exact vs
   local; `fact rows == distinct pk` (no dups); invariants all 0 (hash-consistency,
   orphans, phantoms, unresolved identifiers, junk standards, double-space);
   RLS policy present on all 9 cubes + fact/dim, functionally tested via the
   **tenant role** (`SET ROLE authenticated; SET app.current_school_id=...;` sees
   only that school; no-ctx = 0), not `service_role` (bypasses RLS).

## Method B — surgical targeted change (add/remove specific assessments)

Used 2026-07-13 to remove the HW Spiral Review homework (Fatima). Pattern:

1. **Archive** the affected rows on both DBs (`CREATE TABLE backups.<name> AS
   SELECT * FROM fact WHERE item_id IN (...)`) — retention before any delete.
2. **LOCAL, durably:** add to the correct seed (`fact_row_exclusions` to drop rows,
   `item_label_overrides` to relabel) so a future rebuild honors it; apply to the
   local DB; delete from the local derived layer (`fact`, `dim_subject` [keyed by
   `subject_id`/`item_name` — NO `item_id` column], `dim_item`, `dim_question_data`,
   `dim_unit_lesson`); rebuild `--tag hash` then `--tag cubes` (fast on local, no
   pooler) so rollups (esp. `cube_user_summary.*_by_overall`) recompute clean.
   Verify: items gone, phantoms 0.
3. **PROD:** delete the same item rows from `fact`, `fact_student_submissions_hash`,
   `dim_subject`, `dim_item`, `dim_question_data`, `dim_unit_lesson` (fast — item_id
   index). Then **reload the 9 cubes from the now-clean local** (TRUNCATE + chunked
   COPY) rather than rebuilding cubes on prod (cube rebuild = long-statement pooler
   risk). `VACUUM (ANALYZE)` the cubes. `fact_hash` stays consistent via the direct
   delete (deterministic; no reload needed).
4. **Verify** prod == local (per-school baseline, item gone from fact + cubes,
   phantoms 0) and commit the seed change (seeds don't trigger the migration CI).

---

## Backend / code deploys

Merge to `main` (fast-forward if the branch was built on main) + push. This triggers
(a) the migration CI — verify `supabase db push --dry-run` would apply only intended
migrations (compare prod `supabase_migrations.schema_migrations` vs the repo folder),
confirm each is non-destructive (`CREATE TABLE`, not data mutation); and (b) Railway
auto-redeploy of the backend. Run the report tests first
(`backend && ./venv/bin/python -m pytest tests/reports -q` — the READ-ONLY suite;
the broad suite TRUNCATEs the dev DB). Verify `/health` + deployed commit after.

---

## Open items / pending decisions (as of 2026-07-13)

- **Rotate the prod DB password** — used heavily during the reload. Needs the
  Supabase dashboard (no reset API tool; `ALTER USER` would break the pooler),
  then update Railway `DATABASE_URL` + the GitHub `SUPABASE_DB_PASSWORD` secret in
  the same step, or the backend breaks. Precautionary (never leaked).
- **Fatima misfiling #1/#2** (Inherited Traits / Plant Needs 'Genius Challenge',
  currently Science/Grade 1 on prod): she asked to REMOVE, but confirm whether that
  also removes the pre-existing legitimate Grade-1 copy (they're merged under one
  card) before acting. **#5** (Through an Animal's Eyes, ELA/Grade 6 ✓) still has no
  section/teacher assigned. See `[[project_misfiling_todo]]`.
- Deferred-by-design (need customer/case-by-case, NOT bulk): 36 dim_item-gap
  assessments (~474 students), >100% score rows, grading contradictions.
