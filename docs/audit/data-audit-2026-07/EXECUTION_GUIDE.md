# GAINS Data Remediation — Execution Guide

**Audience:** the engineer(s) executing the remediation. **Status of this document:** advisory playbook; no fix has been applied yet. Authored as an advisory pass (read-only) reviewing the audit + draft plan + code + prod runbook.

**Companion documents (read alongside; this guide does not duplicate their full text):**
- `docs/audit/data-audit-2026-07/REMEDIATION_PLAN.md` — the WHAT (findings F-A1…F-G6, workstreams A–H)
- `docs/audit/fixes/02_assessment_misfiling_prod_runbook.md` — the authoritative prod-replay SQL patterns ("runbook 02")
- `docs/audit/data-audit-2026-07/audit_findings.json` + `evidence/` — per-finding proof
- `CLAUDE.md` — project rules (repository pattern, verification commands)

**Scale context:** 3,700 assessments total; ~407 with real teacher-visible corruption; 484 additional with zero standards tagged (source gap — looks empty, not wrong; do not count these as corruption). Schools: Athenian (1,294,185 fact rows — legacy digit-for-digit anchor), CFP (241,653), Crestwell (111,150). All corruption clusters into six mechanisms (M1–M6); fix the mechanism, not the symptom.

---

## 1. START HERE — the immediate next step (today)

**Action: close the cross-tenant security hole (F-B1 + F-B2). It is the only live *leak* in the findings, it requires zero data mutation, it cannot move any KPI, and everything needed already exists on `main`.**

Verified state as of this audit:
- `cube_question_summary_overall_by_item` on local: `relrowsecurity = false`, **0 policies**. Every sibling cube: RLS enabled + 2 policies. Any authenticated single-school session can read all 3 schools' 68,548 rows.
- The fix already exists and is **merged to main**: `supabase/migrations/20260617120000_cube_question_summary_overall_by_item_rls.sql` (commit `fc5947c`), idempotent (`ENABLE ROW LEVEL SECURITY` + `service_role_full` + `tenant_iso_select` keyed on `app.current_school_id`). It simply was never applied to this DB — the local migration ledger (`supabase_migrations.schema_migrations`) stops at `20260507000100` (17 applied vs 29 files in `supabase/migrations/`). **Do not** run a blanket `supabase db push` against this hand-modified DB; apply the one file directly.
- 27 `*_bak`/`fix*`/`mrg_bak*`/`clean_bak*`/`dqdclean_bak` tables grant `anon` + `authenticated` ALL privileges, 6 containing student PII.

**Exact commands (local):**

```bash
# 1. Apply the idempotent RLS migration (safe to re-run)
psql "postgresql://postgres:postgres@127.0.0.1:56322/postgres" \
  -f supabase/migrations/20260617120000_cube_question_summary_overall_by_item_rls.sql

# 2. Revoke backup-table grants (capture current grants first for rollback)
psql "postgresql://postgres:postgres@127.0.0.1:56322/postgres" -c "
DO \$\$ DECLARE t text;
BEGIN
  FOR t IN SELECT tablename FROM pg_tables WHERE schemaname='public'
           AND (tablename LIKE '%\_bak%' OR tablename LIKE 'fix%'
                OR tablename LIKE 'mrg_bak%' OR tablename LIKE 'clean_bak%'
                OR tablename LIKE 'dqdclean_bak%')
  LOOP EXECUTE format('REVOKE ALL ON TABLE public.%I FROM anon, authenticated', t);
  END LOOP;
END \$\$;"
```

**Acceptance checks (all three must pass):**

```sql
-- (a) RLS parity: must return t | 2
SELECT relrowsecurity,
       (SELECT count(*) FROM pg_policies
         WHERE tablename='cube_question_summary_overall_by_item')
FROM pg_class WHERE relname='cube_question_summary_overall_by_item';

-- (b) Grant lockdown: must return 0 rows
SELECT table_name FROM information_schema.table_privileges
WHERE grantee IN ('anon','authenticated')
  AND (table_name LIKE '%bak%' OR table_name LIKE 'fix%');
```

(c) **Tenant-role validation** (RLS is invisible to psql-as-postgres): log in to the app as a CFP user and open a Standards Deep Dive report — the strand treemap and per-standard bars must render **non-zero** (this table feeds them; the known failure mode of "RLS enabled + policy misconfig" is a deny-all that renders 0.0% tiles — see the migration header comment). Then confirm via the backend API that a CFP session returns only CFP rows from an SDD endpoint.

**Then, same day, on prod:** check the same table's state (`railway run` / prod psql, query (a) above). Prod may be in *either* failure mode — RLS-off (leak) or RLS-on-with-0-policies (deny-all, SDD broken). The same idempotent migration fixes both. Also run the prod backup-table inventory (`_premig`, `*_gai13bak`, `relbl_bak_*`, `mrg_bak_*`, `clean_bak_*`) and revoke `anon`/`authenticated` there too. Do **not** DROP any backup table yet — they are named rollback anchors in runbook 02 (§7 covers when to drop).

**Also today, in parallel:** open PR-1 (the retake ORDER BY fix — Phase 1 below). It is three one-line edits and the single biggest teacher-visible win.

---

## 2. Guiding safety rules (apply to every step below)

1. **Backup before mutate.** Every data mutation is preceded by a `*_bak` snapshot of the exact rows to be touched (`CREATE TABLE <fix>_bak_<table> (LIKE <table>); INSERT … SELECT … WHERE <scope>`), and wrapped in `BEGIN … COMMIT`. Never mutate outside a transaction. Keep baks until the corresponding prod replay is verified.
2. **KPI-baseline conservation.** After every rebuild/mutation, re-check the anchors and explain every delta. The anchors, captured 2026-07-11 on local (re-capture immediately before each phase):

   | School | fact rows | distinct students | distinct item_ids | dim_subject | dim_item |
   |---|---|---|---|---|---|
   | Athenian | 1,294,185 | 555 | 2,547 | 1,255 | 2,547 |
   | CFP | 241,653 | 441 | 734 | 360 | 734 |
   | Crestwell | 111,150 | 262 | 419 | 223 | 419 |

   Plus the legacy digit-parity anchors encoded in `backend/tests/reports/test_report_calculations.py` (`test_week2_canonical_kpis`, `test_twin_invariant_holds`, `test_cqso_one_row_per_ukey`, …). **Athenian is the legacy digit-for-digit anchor: it must not move except where a fix intends it to, and every intended move is written down before the change is made** (e.g. "Crestwell distinct students 262 → 257 when F-D3 removes the 5 demo accounts").
3. **RLS-aware validation.** `psql` as postgres and service_role **bypass RLS**. A fix is only "verified" when the number a *teacher* sees is right: validate through the tenant-role backend (Playwright browser session or API calls carrying a tenant JWT so `app.current_school_id` is set). Direct SQL is for diffing, not for sign-off.
4. **Local first, prod by replay.** Prod has **no raw/staging layer**. Running the pipeline there wipes data. Every data fix: apply on local → verify → capture the exact scoped SQL → replay to prod per runbook 02 (scoped SQL + `--tag cubes` rebuild only). Never `--tag staging|dimensions|facts` on prod.
5. **Override-seed, not UPDATE.** Local *does* have a pipeline, so any in-place UPDATE on local is erased by the next full rebuild. Durable source-data fixes must be expressed in the seed/override layer so rebuilds re-produce them. **Where a fix belongs:**
   - **Code (repo PR):** anything that is a read-layer bug (M1, M2, F-A4/A5/A6) or a transformation-logic bug (M4 prevention F-C1/C2/C3/C4, staging normalization F-F1/F-F2). Self-healing on deploy + rebuild.
   - **Override seed (+ migration if a new table):** anything where the *source data* is wrong and we intentionally deviate from it (M3 misfiles, twin label unification, sandbox-account exclusion, junk assessment_type mapping). Note: today's override tables (`subject_overrides`, `subject_course_overrides`, `school_grade_overrides`, `teacher_pair_overrides`, applied in `01_staging/stg_student_submission.sql:65-102`) match on folder-grade/subject or course-name regex only — **there is no item-level override vehicle yet; Phase 4 creates one** (`item_label_overrides`).
   - **Rebuild:** anything stale-derived (M5). Never fix a cube row by hand; fix the input, rebuild the cube.
   - **One-off scripted data fix (bak + committed replay script):** only for things structurally inexpressible as seed overrides (e.g. deleting overlapping-twin duplicate fact rows, points repairs) — and each such script must be committed under `docs/audit/fixes/` so it can be replayed after any local rebuild and on prod.
6. **`SET statement_timeout = 0`** at the start of every cube-rebuild session (prod default 2 min will kill it). `ANALYZE` between layers.
7. **Never hardcode local IDs in prod SQL.** `subject_id`/`item_id` vintages differ; always look up by business key on the target DB (runbook 02 golden rule) and re-confirm each finding on prod before fixing it there (runbook Step 1 re-audit).
8. **Verification commands after any backend change:** `cd backend && ./venv/bin/python -m ruff check app/ --fix && ./venv/bin/python -c "from app.main import app; print('OK')"` and the `backend/tests/reports` suite.

---

## 3. The full sequenced roadmap

```
                         ┌────────────────────────────────────────────────┐
 TODAY  ──►  Phase 0     │ Security: B1 RLS apply (local+prod), B2 revoke │  independent, ops-only
             (hours)     └────────────────────────────────────────────────┘
                         ┌────────────────────────────────────────────────┐
 TODAY  ──►  Phase 1     │ PR-1 retake ORDER BY (F-A1/A2) + G1 fixture    │  pure code, parallel PRs,
             (days)      │ PR-2 merge worktree-temporal-orbiting-sketch   │  deploy to prod as soon as
                         │      (F-A3 zero-poisoning + F-A4 YTD)          │  each is reviewed
                         │ PR-3 alignment-quality rework (F-A5)           │
                         │ PR-4 browse_students school_id (F-A6)          │
                         └───────────────┬────────────────────────────────┘
                                         │  (data work serializes on the one local DB from here)
                         ┌───────────────▼───────────────┐
             Phase 2     │ Standards seed (F-E1..E6)     │  REBUILD #1: dim_standard/dim_strand
             (2-4 days)  │ purge collisions, regen exact │  + fact identifier re-join + cubes
                         └───────────────┬───────────────┘
                         ┌───────────────▼───────────────┐
             Phase 3     │ Pipeline structural (F-C1..C6 │  REBUILD #2: full local pipeline
             (3-5 days)  │ + F-F1/F-F2 staging normal-   │  orphan=0, twin diff review,
                         │ ization pulled forward)       │  KPI baseline diff (riskiest step)
                         └───────────────┬───────────────┘
                         ┌───────────────▼───────────────┐
             Phase 4     │ Data corrections (F-D1..D8)   │  REBUILD #3: item_label_overrides seed
             (3-5 days + │ via NEW item_label_overrides  │  + scripted fixes + cubes
             gate waits) │ + scripted point/row repairs  │  gates: D3 Crestwell, D1 Chapter-1
                         └───────────────┬───────────────┘
                         ┌───────────────▼───────────────┐
             Phase 5     │ Hygiene remainder (F-F3..F7)  │  cubes-only rebuild
             (1-2 days)  └───────────────┬───────────────┘
                         ┌───────────────▼───────────────┐
             Phase 6     │ Guardrails consolidation (G*) │  lands incrementally 1→5, gate here
                         └───────────────┬───────────────┘
                         ┌───────────────▼───────────────┐
             Phase 7     │ PROD REPLAY (runbook 02)      │  scoped SQL + --tag cubes only
                         └───────────────────────────────┘
```

**Dependency rules that drive this order:**
- **Standards seed (Phase 2) before any big cube rebuild** — otherwise you rebuild cubes on polluted identifiers twice.
- **`dim_item` derivation fix (F-C1) before re-checking orphans** — the 29-orphan finding is *dissolved* by F-C1, not patched row-by-row. Re-run the orphan query only after Rebuild #2.
- **F-F1 assessment_type normalization and F-C2 partition hardening before F-D2 twin data-fixes** — normalization + partition fix collapse several twin sets automatically at rebuild; only then enumerate what still remains and fix that smaller set. (Fixing twins first would waste effort on rows the rebuild re-splits or auto-heals.)
- **Phase 4 override seeds after F-C2** so a rebuild can never re-mint the twins the overrides unify.
- **Code PRs (Phase 0/1) never wait on data phases** — they deploy to prod immediately and independently.
- **Critical path:** Phase 2 → 3 → 4 (each ends in a rebuild + baseline diff on the single shared local DB; do not interleave). Phases 0/1 are off-path. Phase 5 can partially overlap 4's gate waits. Phase 7 replays 2–5's verified state.

---

## 4. Per-phase execution playbook

### Phase 0 — Security (F-B1, F-B2) — done per §1 above

Rollback: `ALTER TABLE … DISABLE ROW LEVEL SECURITY` / re-`GRANT` from the captured privilege snapshot (save `information_schema.table_privileges` output to the audit dir before revoking). Prod replay: same two commands + prod inventory; **rotate the prod DB password after the ops session** (runbook Step 7). Track the 10 additional RLS-off tenant tables (staging/ingestion/lti — finding #55, latent) in the G5 parity guardrail rather than fixing ad hoc now.

### Phase 1 — Read-layer code (M1 + M2) — four independent PRs

**PR-1 (F-A1/F-A2): retake determinism.** In `backend/app/repositories/cube_repository.py`, three `fact_dedup` CTEs pick an arbitrary attempt. Insert `submission DESC NULLS LAST` as the **first tiebreak after the DISTINCT ON keys**:
- `:215` — `ORDER BY user_uid, question_id, position_number, submission DESC NULLS LAST, identifier NULLS LAST`
- `:529` — identical change
- `:2317` — `ORDER BY fss.user_uid, fss.item_id, fss.question_id, fss.position_number, fss.submission DESC NULLS LAST, fss.standard NULLS LAST`

This mirrors the proven pattern used seven times in `backend/app/repositories/student_repository.py` (`:104, :150, :252, :294, :334, :394, :435`). Include the **G1 regression fixture**: a 2-attempt synthetic student (attempt 1 wrong / attempt 2 right) asserting every read path (QRA KPI strip, per-question rows, YTD matrix, per-student report) returns the attempt-2 score.
*Pre-change snapshot:* none needed (code only). *Verification:* CFP "Module 4 Assessment: Better Together" KPI correct-% moves **65.77% → 71.50%**; the per-student report and assessment report now agree for retake students; two consecutive API calls return identical numbers; `backend/tests/reports` green. *Rollback:* revert commit. *Prod:* normal deploy; self-heals (affects 308 assessments / 194 item report cards).
*Note:* this implements **latest-attempt** policy (legacy-faithful). Decision gate DG-1 (§8) may later switch to best-attempt — that is a one-line tiebreak change (`points_received DESC` first); do not wait for it.

**PR-2 (F-A3/F-A4): merge branch `worktree-temporal-orbiting-sketch`.** The zero-poisoning fix **already exists** there — commits `d4c099c` (Standard Summary parity), `221bb10` (Strand Summary parity), plus `6fe99b3` (YTD → `cube_user_summary` pivot), `8f826d5`, `9932554`. Do **not** re-implement. The diff is large (20 files, +639/−1996, deletes legacy strand/standard frontend components, rewrites 574 lines of `cube_repository.py`) — review it as a feature merge, not a hotfix:
1. Confirm the `ukey`-bridge `AVG(COALESCE(grade_average, 0))` is replaced by the standard-code bridge and that unmatched codes are **excluded**, not zeroed.
2. Confirm F-A4 is resolved: grep the branch for `dqd.subject =` / `qd.grade =` filters in `get_ytd_longitudinal_cells` / `get_ytd_longitudinal_standard_units` — the rewrite must scope through `dim_item.subject_id → dim_subject` (the `_QS_SCHOOL_FILTER_SQL` pattern, `cube_repository.py:19-35`) or via `cube_user_summary`. If any direct `dqd.subject` filter remains, the 14 CFP HS course-override subjects still lose their standards dimension — fix before merge.
3. Capture before/after API responses for: one known zero-poisoned standard (75–94% true vs 7–20% shown), the Standard/Strand KPI strips on an Athenian anchor assessment (must match legacy), and YTD for a CFP HS course (must show real standards columns, not one "Other").
*Verification:* the 813 deflated standard/strand rows recover; Athenian anchors unchanged; tenant-role Playwright screenshot sweep of Standard Summary / Strand Summary / YTD pages. *Prod:* normal deploy.

**PR-3 (F-A5): alignment-quality list.** `list_alignment_quality_by_item` (`cube_repository.py:2004-2056`): replace `MAX(dqd.subject)/MAX(dqd.grade)` with subject/grade from `dim_subject` via `dim_item.subject_id`; derive the question universe from `cube_question_summary`/fact `LEFT JOIN dqd` so dqd-missing questions count as **unaligned** instead of vanishing. Same treatment for `get_school_alignment_quality`'s direct dqd filters (`:1947-1951`). *Note:* numbers become fully correct only after F-C1 fixes `dim_item.subject_id` divergence — ship the code now, re-verify after Rebuild #2.

**PR-4 (F-A6):** add `AND dst.school_id = <fact school_id>` to the `browse_students` join. Hardening only.

### Phase 2 — Standards seed (M6: F-E1..E6) → Rebuild #1

**Objective:** one clean `dim_standard`, correct identifiers on every fact row, correct descriptions/labels.
**Files:** `supabase/seeds/dim_standard.csv`, `refresh_standards.py`, `augment_standard_aliases.py`, `resolve_cpalms_links.py`, `load_standards.py`; `05_dimensions_d/dim_strand.sql`. Read `docs/audit/legacy-schoology-cpalms-mapping.md` + `docs/audit/edvancelearning-ims-integration.md` first (per CLAUDE.md doc index). Note the *live* joins are already exact-match (`07_facts/fact_student_submission.sql:206-215`, `04_dimensions_c/dim_question_data.sql:71-91`) — the pollution is **in the seed rows themselves** (legacy ILIKE-minted alias rows).

Order of operations:
1. **F-E5 + F-E1:** purge the 3 exact-dup alias rows, 27 junk numeric codes, and the 44-code collision set (alias rows whose identifier's canonical code contradicts the `schoology_standard` trailing segment); regenerate aliases with **exact-match** synthesis in `refresh_standards.py`; add `UNIQUE(identifier, schoology_standard)` + code-format check to the refresh script.
2. **F-E2:** add curated rows for the 264 missing real codes (map retired codes to nearest current benchmark or synthesize alias rows).
3. **F-E3:** backfill descriptions for the **24 referenced** NULL-description codes first (extend `resolve_cpalms_links.py` to scrape archived CPALMS description text), rest opportunistically.
4. **F-E4:** HTML-entity decode on `dim_strand.strand` and `dim_standard.strand/description/cluster` display columns — **never touch `strand_id`** (hash join key). Note `8f826d5` on the PR-2 branch already decodes at the read layer; fixing the seed is still correct (belt and braces).
5. **F-E6:** null/flag the 3 bare-word "standards" at parse/staging.

**Pre-change backup:** `CREATE TABLE e_bak_dim_standard AS TABLE dim_standard;` (+ dim_strand). Snapshot the current fact identifier distribution: `SELECT identifier, count(*) FROM fact_student_submission GROUP BY 1` to a CSV for diffing.
**Rebuild #1 (local):** reload seed (`load_standards.py`), then `cd backend && ./venv/bin/python -m app.transformations.runner --tag dimensions` (rebuilds dim_question_data/dim_strand identifiers), `--tag facts`, `--tag hash`, `--tag cubes` (with `statement_timeout=0`).
**Verification:**
- `SELECT schoology_standard FROM dim_standard GROUP BY 1 HAVING count(DISTINCT identifier) > 1` → only legitimate parent/child (a–f sub-parts) remain.
- The 18,220 mis-pinned fact rows now carry the correct identifier; 264-missing count → target ~0; the 24 referenced blank descriptions render text (tenant-role check on a standards report).
- **KPI conservation:** per-question/per-student *points* must be byte-identical (identifier changes cannot move scores) — assert with a pre/post checksum of latest-attempt `(user_uid, question_id, position_number, points_received)`; fact **row counts may shift** where alias fan-out rows were purged — every delta must map to a purged alias. Standard/strand-level averages move *intentionally* — document each.
**Rollback:** restore `e_bak_*`, re-run fact+cubes.
**Prod replay:** `dim_standard`/`dim_strand` are seed-shaped — reload them directly on prod (bak first). Fact cannot be rebuilt on prod: replay as a scoped `UPDATE fact_student_submission f SET identifier = ds.identifier, strand_id = … FROM dim_standard ds WHERE f.standard = ds.schoology_standard AND f.identifier IS DISTINCT FROM ds.identifier` (plus NULL-out for purged junk), then `--tag cubes`.

### Phase 3 — Pipeline structural (M4/M5 prevention: F-C1..C6, + F-F1/F-F2 pulled forward) → Rebuild #2

**Objective:** rebuilds become safe, deterministic, and stop re-minting twins/orphans/vintage conflicts.

- **F-C1 (`dim_item` divergence → dissolves the 29 orphans):** `03_dimensions_b/dim_item.sql:69-91` keeps the *first-occurrence* bucket (`ORDER BY assessment_date ASC`) from staging while fact keeps the *latest-export* bucket. Fix by deriving `dim_item.subject_id` from the same rows that survive fact's `latest_export` prune — **recommended shape: rebuild `dim_item` from `fact_student_submission`** (also makes `dim_item` re-derivable on prod, which has fact but no staging). Acceptance: the orphan query returns **0 | 0** (today: 29 | 7,730):
  ```sql
  SELECT count(DISTINCT f.subject_id), count(*)
  FROM fact_student_submission f
  LEFT JOIN dim_item di ON di.subject_id = f.subject_id
  WHERE di.subject_id IS NULL;
  ```
- **F-C2 (twin prevention):** `07_facts/fact_student_submission.sql:159-162` — the `latest_export` `PARTITION BY (school_id, user_uid, item_id, question_id, position_number, sub_question, submission)` omits grade/subject/assessment_type/session. Add `grade` first; decide on the others from diff evidence (DG-9). **This is the highest-KPI-risk change in the entire remediation** — it prunes rows that previously survived. Mandatory: full row-level pre/post diff keyed on `(school_id, item_id, user_uid, question_id, position_number, submission)`; **every pruned row must be explained as a known cross-label twin/remnant** (e.g. the CFP "Topic 8" Higher-Ed 1-student fragment). If any Athenian anchor row is pruned unexplained, stop and re-scope.
- **F-C3 (dqd vintages):** apply latest-export-wins to `dim_question_data` (one row per `(school, question_id, position)`); add `AND q.item_id = f_meta.item_id` to the cube lateral join and prefer the dqd row whose `correct_answer` matches fact. Fixes the 594 wrong displayed correct answers **at rebuild** (they are a symptom, not separate data fixes).
- **F-C4:** guard the same-name merge in `cube_question_summary.sql` — only collapse across items when normalized question text/`question_id` matches (`n_distinct_texts > 1` exclusion). 302 slots / 68 assessments stop blending unrelated questions.
- **F-C5:** canonicalize `user_name` per `(school_id, user_uid)` to latest-attempt name at fact build; `dim_student` takes newest vintage.
- **F-C6:** either apply `cube_question_summary`-style pre-aggregation to `cube_user_summary`/`cube_standard_summary` score/total columns **or** (cheaper, acceptable) mark them deprecated in the SQL header + add a QA assertion that no repository query reads them. `total_questions`/`total_standards` KPIs must not move.
- **F-F1/F-F2 (pulled forward, staging layer):** whitespace/junk `assessment_type` normalization (trim/collapse; map `'2 sectionsAll Sections'`, `'Lesson  Assessments'` → `'Lesson Assessments'`, etc.) and section-label normalization (map by `section_nid` → `dim_section.section_name`, backfill NULLs, `COALESCE` at cube build) in `01_staging/stg_student_submission.sql` / `stg_question_data.sql` + an override-map for junk values. **This immediately un-splits several F-D2 twin sets** — that is why it precedes Phase 4.

**Backup:** full snapshots of `dim_item`, `fact_student_submission`, `dim_question_data` row-count/checksum profiles (not full copies of 1.6M rows — keyed checksums are enough since the pipeline can regenerate local).
**Rebuild #2:** full local pipeline (`--tag staging` → `dimensions` → `facts` → `hash` → `cubes`).
**Verification:** orphan = 0|0; `backend/tests/reports` green (twin invariant, cqso one-row-per-ukey, Q12 multi-select invariant still 0); KPI baseline table §2 re-captured and every delta mapped to an intended fix; re-run the audit's twin detector — the twin count must **drop** (label-drift twins collapsed) with the remainder enumerated for Phase 4; tenant-role spot-check of one previously-fragmented assessment.
**Rollback:** git revert the transformation SQL + re-run pipeline (local pipeline = the rollback mechanism; that is the luxury prod does not have).
**Prod replay:** structural SQL ships as code (affects future local rebuilds); the *data consequences* replay to prod as scoped SQL — dim_item corrections via the rebuild-from-fact script (runnable on prod since it reads fact), fact row prunes via scoped `DELETE` with bak (only the enumerated twin-remnant rows), dqd dedupe via scoped `DELETE`/`UPDATE` with `dqdclean`-pattern bak — then `--tag cubes`.

### Phase 4 — Data corrections (M3 + M4 data: F-D1..D8) → Rebuild #3

**Create the durable vehicle first (this is new work the plan implies but does not spell out):**
- Migration: `item_label_overrides (school_id uuid, item_id text, subject_override text, grade_override text, assessment_type_override text, item_name_override text, reason text, source text, PRIMARY KEY (school_id, item_id))` — mirror the shape/conventions of the existing override tables.
- Seed file: `supabase/seeds/item_label_overrides.sql` (sibling of `subject_grade_overrides.sql`, same school-resolution subquery pattern).
- Staging join: apply in `01_staging/stg_student_submission.sql` **and** `stg_question_data.sql` (both carry `item_id`), with precedence **item-level override > course override > subject/grade override** (extend the existing `COALESCE` chain at `stg_student_submission.sql:65-70`).
- Because `subject_id = uuid_6(school, subject, assessment_type, grade, session, item_name)` is computed *after* staging, an item-level label override automatically (a) relabels misfiles and (b) merges label-drift twins into one `subject_id` at every future rebuild. That is the whole point.

**Then the corrections:**
- **F-D1 (12 misfiles):** seed override rows for 11 now; **hold the Crestwell "Chapter 1 Test" until DG-3 resolves.** Get the targets right: the two "HW Spiral Review" 4th-Period copies (`7626433775`, `7628347421`) go to **Grade 6** (not 7 — corrects the existing doc); the 2nd-Period copies stay Grade 7; the two new CFP Pre-Algebra Topic 1 items (`7964065626` = 256 rows, `7964067882` = 360 rows, currently Math/Grade 7 — re-verified live) follow Topics 2–7 to Algebra/Grade 8. Update `docs/audit/assessment_misfiling_audit.md` with the 2 new items. Evidence: `evidence/section-teacher-integrity.csv`, `evidence/STI-1-repro.csv`.
- **F-D2 (twins, post-Rebuild-#2 remainder):** for same-item label twins → `item_label_overrides` rows. For distinct-item twins (44 duplicate pairs), a label override unifies them under one `subject_id` (subject_id excludes item_id), which fixes the split report cards; for the **overlapping-student** pairs with contradictory scores, additionally prune to newest vintage per student+question — this is a scripted fact `DELETE` (bak + committed replay script), since overrides cannot express row exclusion. If more than ~a handful of rows need this, propose a small `fact_row_exclusions` seed applied at fact build so it survives rebuilds. Cross-item `question_no` mapping for Crestwell chapter-1 per plan.
- **F-D3 (Crestwell demo cluster):** **blocked on DG-2.** Prepare both halves now: the ingest-time exclusion (sandbox section/instructor names — durable) and the phantom-cleanup+heal script (runbook §Step 4 pattern — data). Execute on confirmation. Intended delta: Crestwell distinct students −up to 5.
- **F-D4/D7 (points):** case-by-case on ~12 + ~20 items; reconcile to newest-export authority; cap or restore from dqd/legacy parquet; scripted with bak. Set the `points_possible = 0` policy explicitly (product decision, small).
- **F-D5 (heal re-audit):** derive the true heal population from `clean_bak_*`/`mrg_bak_*`/`relbl_bak_*` — **never by `file_name`** (it is empty on 100% of fact rows; the prune runs on staging at build time — plan §7). Backfill recoverable, delete unrecoverable NULL-points stubs, rescale the 66/11 rows.
- **F-D6:** backfill the 33 missing dqd rows (any vintage containing them, else synthesize minimal `question_no`/`total_points` from fact); decide the 4 dqd-only Crestwell questions.
- **F-D8 (3,605 grading contradictions):** **triage only, never bulk-fix.** Produce a reviewed narrow batch (start with the clearest regrade collisions from `evidence/p3_grading_contradictions.csv`), get DG-10 sign-off, apply as scripted fixes. Everything not clearly a collision stays untouched (partial credit is legitimate).

**Rebuild #3:** full local rebuild (proves the overrides are durable — this rebuild must *reproduce* the fixes, not undo them), then re-apply the committed exclusion/points scripts, then cubes.
**Verification:** runbook §6 **card==fact gate for every touched `subject_id`** (SUMX card = distinct fact headcount, dim_items > 0); misfiled items appear under correct subject/grade in a tenant-role session; twin count at target; KPI deltas all intended.
**Prod replay:** runbook 02 Steps 2–5 verbatim (relabel / twin-merge / phantom+heal / dqd-cleanup patterns), IDs looked up by business key on prod, one transaction per fix with `*_bak`, then `--tag cubes`. Also seed `item_label_overrides` on prod (inert without a pipeline, but keeps environments declaratively identical).

### Phase 5 — Hygiene remainder (F-F3..F7)

F-F3 instructor-exclusion list at `dim_item`/`dim_section` build (`'GAINS Admin'` now; Sitara merge **blocked on DG-4**). F-F4 `grade_sort` ordering with explicit band ranks. F-F5 mojibake/whitespace cosmetics (display-only; keep verbatim if strict legacy parity preferred). F-F6 `dim_section` latest-snapshot-wins. F-F7 `'HS Alegra II'` **blocked on DG-5**. Cubes-only rebuild; label-only KPI deltas (none numeric).

### Phase 6 — Guardrails consolidation (see §6)  ·  Phase 7 — Prod cutover (see §7)

---

## 5. Data-fix mechanics — pattern → finding map

The four reusable patterns are fully specified in runbook 02; reuse them verbatim (do not invent new SQL shapes):

| Runbook pattern | SQL shape (runbook §) | Used by |
|---|---|---|
| **Relabel** (keep `subject_id`, fix subject/grade columns across `dim_subject`, fact, `cube_question_summary`, `cube_user_summary`, dqd) | Step 2 | F-D1 misfiles (prod replay); F-F7 if approved; F-F1 junk-type relabels on prod |
| **Twin merge** (reassign `subject_id` A→B across fact, `dim_item`, 4 cubes; fix labels; DELETE A's `dim_subject`; then card==fact + heal check) | Step 3 | F-D2 twin sets (prod replay); Phase-3 twin remainders |
| **Phantom cleanup + heal** (delete 0-fact `dim_subject`+`dim_item`, immediately re-INSERT any `dim_item` a real assessment still needs — **always as one pair**) | Step 4 | F-D3 demo cluster; any post-merge ghost cards; F-D5 stub deletion side-effects |
| **dqd cleanup** (delete pure duplicates, relabel to the fact-bearing `dim_subject` label, `dqdclean_bak` first) | Step 5 | F-C3 prod replay; F-D6 backfill counterpart; Phase-4 label sync |

On **local**, the durable expression of relabel/twin-merge is the `item_label_overrides` seed (+ rebuild); the runbook UPDATE patterns are the **prod** replay of the same fact. On **prod**, the runbook patterns are the only option. The **card==fact verification** (runbook §6) runs after *every* use of any pattern, both environments.

**Do NOT touch without human/customer confirmation** (gates in §8): the Crestwell "Chapter 1 Test" grade (DG-3), the Crestwell staff/demo deletions (DG-2), the Sitara identity merge (DG-4), the `'HS Alegra II'`/`'Calculas'` relabels (DG-5), any switch away from latest-attempt semantics (DG-1), the F-D8 contradiction batch (DG-10). Also **do not blind-sweep the 36 `dim_item`-gap assessments** from runbook §6 — they are correctly labeled, categorized (20 REASSIGN / 14 MERGE-TYPE / 2 CONFLICT), and need case-by-case merges; schedule them inside Phase 4 as their own reviewed sub-batch, expecting F-C1 to change (and likely shrink) the list first.

---

## 6. Verification & guardrails to institutionalize (Workstream G)

Land these as code so the corruption classes cannot silently return; each is cheap:

1. **G1 — retake fixture** (ships in PR-1): 2-attempt fixture; assert every read path returns the latest attempt. Guards M1.
2. **G2 — post-build pipeline QA assertions** (add to `runner.py` as a final `qa` step or a pytest run after builds): `fact.question_id ⊆ dqd per item` (0 missing); orphan query = 0; `fact.points_possible == dqd.total_points` per question-position; every fact `subject_id` has a `dim_item`; `COUNT(DISTINCT identifier) per schoology_standard ≤ 1` except parent/child. Guards M4/M6/F-D6/F-D7.
3. **G3 — keep the Q12 multi-select invariant test** in the suite (currently 0; must stay 0).
4. **G4 — loud skipped cubes:** `runner.py` `isolate_cubes=True` logs-and-skips a failed cube, silently leaving it stale — the exact M5 mechanism. Change to: fail the run (non-zero exit) and print a `STALE CUBE` banner naming the table; never let a partial cube build look green.
5. **G5 — RLS parity check** (pytest or CI SQL): every `cube_*` and tenant-scoped table has `relrowsecurity = true` and a `tenant_iso_select` policy; zero `anon`/`authenticated` grants on any non-application table. Guards F-B1/B2 recurrence (a future `CREATE TABLE`-style migration without policies gets caught).
6. **G6 — deterministic dedupe tiebreaks:** every `DISTINCT ON`/`ROW_NUMBER` dedupe in repositories and transformations ends with a stable unique key so rebuild outputs are byte-reproducible.
7. **KPI-baseline snapshot script** (formalize what §2 does by hand): a read-only script that emits the anchor table + per-report canonical KPIs for the three schools; run before/after every rebuild and diff. Store snapshots under `docs/audit/data-audit-2026-07/baselines/`.
8. **Coverage badge (F-E7 UI):** surface "N of M questions aligned" on reports so the 86 partially-tagged assessments read as *incomplete* rather than silently wrong, and the 484 zero-tagged read as *untagged* rather than broken.

---

## 7. Production cutover plan

**Standing rules:** prod has no raw/staging — the only rebuild ever run on prod is `--tag cubes` (via `railway run --service backend python -m app.transformations.runner --tag cubes`, session opened with `SET statement_timeout = 0`). All fact/dim changes are scoped SQL in transactions with `*_bak` anchors. Prod Supabase project: `fkeazldazwzdkpwhngbm`.

**Order:**

1. **Immediately (with Phase 0/1):**
   - Verify `cube_question_summary_overall_by_item` RLS state on prod (§1 query (a)); apply migration `20260617120000` if not `t|2`. Then tenant-role check that SDD strand tiles render (guards the deny-all failure mode).
   - Inventory prod backup tables (`_premig`, `*_gai13bak`, `relbl_bak_*`, `mrg_bak_*`, `clean_bak_*`), `REVOKE ALL … FROM anon, authenticated`, and move them to a private `backups` schema (`ALTER TABLE … SET SCHEMA backups`) — prod cannot regenerate them, so they stay as rollback anchors but locked down.
   - Deploy PR-1..PR-4 through the normal pipeline as each merges. These self-heal — no data replay needed.
   - Rotate the prod DB password after the ops session.
2. **Record the prod Step-0 baseline** (runbook Step 0): per-school Total Students cards + the §2 anchor queries, saved before any data change.
3. **Re-audit on prod** (runbook Step 1): prod is a different data vintage — re-run the standards-vs-label audit and the twin/orphan/misfile detectors on prod; only replay fixes that **re-confirm** there. Expect small differences from local.
4. **Replay in local-phase order**, one batch per transaction-set, cubes rebuilt once per batch:
   a. Standards seed reload (`dim_standard`, `dim_strand`, bak first) + scoped fact `identifier`/`strand_id` UPDATE → `--tag cubes`.
   b. `dim_item` correction script (rebuild-from-fact, runnable on prod) + enumerated twin-remnant prunes → `--tag cubes`.
   c. Relabels / twin merges / phantom+heal / dqd cleanup per runbook Steps 2–5, IDs by business key → `--tag cubes`.
   d. Hygiene relabels → `--tag cubes`.
5. **Post-deploy validation (teacher-visible):** runbook §6 gate for every touched `subject_id` (card==fact, dim_items>0); KPI conservation vs Step-2 baseline with every intended delta listed; tenant-role Playwright sweep of the named fixed reports (Module 4 retake KPI, a previously zero-poisoned standard, the 12 misfiled assessments under their correct subject/grade, a merged twin showing the full class, SDD strand tiles); spot-check vs legacy PDFs for Athenian.
6. **Close out:** rotate the prod DB password again if credentials were handled during ops; keep all `*_bak`/`backups.*` tables; schedule their DROP for 2–4 weeks after the last replay batch is verified stable (DG-8) — the local 27 (6 with PII) get dropped at the same milestone.

---

## 8. Decision gates & open questions

| # | Decision | Owner | Blocks | Default until decided |
|---|---|---|---|---|
| DG-1 | Attempt policy: latest (legacy-faithful) vs best/highest | Product owner | Nothing now; would re-touch PR-1 tiebreak + the 91-cell case | Ship **latest** (matches `student_repository`) |
| DG-2 | Crestwell staff/demo accounts are internal test accounts? | Crestwell/Edvance | F-D3 deletions (5 students, 72-row phantom session) | Prepare scripts, do not execute |
| DG-3 | Crestwell "Chapter 1 Test": Grade 1 vs Grade 2 | Crestwell | 1 of the 12 F-D1 relabels | Fix the other 11 |
| DG-4 | `Sitara Qalander` == `Sitara Shamsheer`? | Customer | Instructor-identity merge half of F-F3 | Exclude `GAINS Admin` only |
| DG-5 | `'HS Alegra II'` / `'Calculas'`: fix vs legacy parity | Product owner | F-F7 (4 subject_ids) | Keep verbatim (parity) |
| DG-6 | CFP Higher-Ed band is intentional convention? | CFP | Nothing (already excluded from heuristics) | Document as convention |
| DG-7 | `Amora Johnson` = two distinct children in two schools | Customer | Nothing | No action |
| DG-8 | Backup-table DROP timing (local 27 + prod set) | Eng lead | Final F-B2 closure | Revoked + schema-moved, retained |
| DG-9 | F-C2 partition scope: `+grade` only, or also subject/type/session | Eng lead (with diff evidence from Rebuild #2 dry-run) | Phase 3 final shape | Start with `+grade` |
| DG-10 | F-D8 narrow contradiction batch approval | Product owner | F-D8 execution | Triage list only, no writes |
| DG-11 | Source-side standards tagging (481 zero + 86 partial) — who fixes in Schoology, and ship the "N of M aligned" badge? | Product + schools | F-E7 closure (not corruption, but closes the "looks empty" complaint) | Badge recommended |

---

## 9. Definition of done

All of the following, checked on **local and prod**, with tenant-role verification where user-visible:

1. **Hard-defect assessments ~407 → near-0:** re-run the audit's full-inventory detector suite; remaining flags are only (a) explicitly deferred gate items (DG-2/3/5/10 if still open), (b) the documented 484/86 source-tagging gaps (surfaced via badge, not silent), and (c) any runbook-§6 case-by-case items consciously deferred with a ticket each.
2. **Mechanism-level invariants:** orphan query = 0|0; twin invariant test green; no `schoology_standard` with >1 identifier (except parent/child); `fact.question_id ⊆ dqd` per item; points reconciliation (fact vs dqd) = 0 mismatches; retake fixture green; Q12 invariant still 0.
3. **Cross-report consistency:** per-student report == assessment report for retake students; Standard/Strand pages reconcile with per-question reports (no zero-poisoned rows); YTD shows real standards columns for all 14 CFP HS courses.
4. **KPI conservation:** §2 anchor table matches baseline except the documented intended-delta ledger (every line signed off); Athenian legacy digit-parity tests green.
5. **Security:** RLS parity check passes on every cube/tenant table (incl. `cube_question_summary_overall_by_item` = `t|2`) on local **and prod**; zero `anon`/`authenticated` grants on non-application tables; prod backup tables in `backups` schema; passwords rotated; backup tables dropped at the DG-8 milestone.
6. **Durability proof:** one full local pipeline rebuild from raw, followed by the committed fix scripts, reproduces the corrected state byte-for-byte (KPI snapshot diff = intended ledger only). This is the test that the override-seed strategy actually worked.
7. **Prod == local** on every touched scope (spot-check via keyed checksums per touched `subject_id`), and the runbook §6 card==fact gate passes for every touched `subject_id` on prod.
8. **Guardrails live:** G1–G6 + baseline-snapshot script merged and running in CI/post-build.

---

## 10. Risk register

| # | Risk | Likelihood/Impact | Mitigation |
|---|---|---|---|
| R1 | **F-C2 partition-key change prunes legitimate rows** and silently moves Athenian anchor KPIs | Medium / Critical | Row-level pre/post diff; every pruned row mapped to a known twin/remnant before COMMIT; start with `+grade` only (DG-9); Athenian digit-parity tests as tripwire; local pipeline = instant rollback |
| R2 | **PR-2 branch merge regresses Standard/Strand/YTD** (it deletes 1,996 lines incl. whole frontend components) | Medium / High | Treat as feature merge: API before/after capture on anchors, Playwright screenshot sweep, `tsc --noEmit` + vitest + report tests; deploy behind a quick-revert plan |
| R3 | **Cube rebuild timeout / partial rebuild leaves a silently stale cube** (the M5 class, re-created during remediation itself) | Medium / High | `SET statement_timeout=0` always; land G4 (loud skipped cubes) *before* the Phase 2 rebuild; post-rebuild row-count sanity per cube |
| R4 | **Override-seed relabels change `subject_id` hashes at rebuild** (labels feed the hash) → stale bookmarks/links, KPI attribution moves between grade/subject buckets | Certain-by-design / Medium | Keep a before→after `subject_id` mapping table per rebuild; verify report *lists* via tenant role (cards are looked up fresh, not hardcoded); include moves in the intended-delta ledger |
| R5 | **Prod has no pipeline; an accidental staging/fact run wipes prod** | Low / Catastrophic | Never run runner tags other than `cubes` on prod; add a runner guard that refuses non-cube tags when `raw_*`/staging tables are absent or empty; prod work only via runbook-02 scoped SQL |
| R6 | **Local↔prod vintage drift** makes replayed SQL hit the wrong rows | Medium / High | Runbook golden rules: re-audit on prod first, business-key lookups only, per-fix transactions + baks, card==fact gate after each |
| R7 | **Enabling RLS breaks a code path that doesn't set `app.current_school_id`** (deny-all: blank report instead of leak) | Low / Medium | Post-apply tenant-role SDD smoke test (§1 check c); G5 keeps parity thereafter |
| R8 | **Standards regeneration leaves mixed identifier vintages** across fact/dqd/cubes (M5 again) | Medium / High | Phase 2 is one atomic sequence: seed reload → dims → fact identifier → cubes in a single supervised session; checksum assertion that points are byte-identical |
| R9 | **Dropping backup tables before prod replay is verified** destroys the only rollback anchors (prod can't re-derive anything) | Low / Critical | F-B2 is split: revoke+schema-move now, DROP only at DG-8 milestone after stability window |
| R10 | **Gate-blocked fixes applied without sign-off** (Crestwell deletions, Chapter-1 grade, Sitara merge, Alegra II) put wrong-but-confident numbers in front of schools | Low / High | §8 table is the checklist; Phase-4/5 scripts for gated items live in the repo but are executed only with the gate recorded in the fix log |

---

### Critical files for implementation

- `backend/app/repositories/cube_repository.py` — M1 retake fix (`:215`, `:529`, `:2317`), F-A4/A5 scoping fixes, `_QS_SCHOOL_FILTER_SQL` pattern (`:19-35`)
- `backend/app/transformations/07_facts/fact_student_submission.sql` — `latest_export` partition hardening (`:159-162`), fact identifier join
- `backend/app/transformations/03_dimensions_b/dim_item.sql` — first-occurrence → latest-export derivation fix (dissolves the 29 orphans)
- `supabase/seeds/subject_grade_overrides.sql` — the override-seed pattern to extend with the new `item_label_overrides` vehicle (+ `01_staging/stg_student_submission.sql:65-102` where it is applied)
- `docs/audit/fixes/02_assessment_misfiling_prod_runbook.md` — the four prod-replay SQL patterns every Phase-4/7 data fix must reuse
