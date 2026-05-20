# 04 — Dimensions Audit

Scope: stages 02–06 of `backend/app/transformations/` (the 14 dim_*.sql files) and the matching DDL in `supabase/migrations/20260507000050_dim_tables.sql` + standards seed `supabase/migrations/20260507000045_standards_seed.sql`. Compared against the PBIX truth source (`data/_pbix_extract/`).

Anchor for impact analysis: Chapter 9 Test, Grade 8, `item_id 8359960427`. Legacy 66.9 / 96.1 / 28.9 vs new 65.4 / 96.3 / 27.8. Per-standard AR.1.7 77.8 vs 78.9, AR.3.1 69.0 vs 69.5.

---

## Coverage matrix

PBIX has only the 5 dims that the report model actually consumes (see `data/_pbix_extract/02_tables.json` lines 14–18 and `08_relationships.csv`). Everything else — `dim_school`, `dim_student`, `dim_section`, `dim_session`, `dim_grade`, `dim_assessment_type`, `dim_course`, `dim_teacher`, `dim_parent`, `dim_unit_lesson` — is built by the upstream Schoology PySpark notebook (`40_schoology_py_spec.md` §4.1–4.7) and feeds the cube/fact builds, but never appears in the PBIX semantic model directly because PBIX pulls those attributes already denormalised inside the cubes.

| Dim                     | Current?                                              | PBIX?                              | Grain match?                                                                 | Notes |
|-------------------------|-------------------------------------------------------|------------------------------------|-----------------------------------------------------------------------------|-------|
| dim_school              | yes (`02_dimensions_a/dim_school.sql:10`)             | no (built upstream in notebook)    | n/a (not in PBIX model)                                                     | One row per UUID `school_id`; PK was changed from CSV `School_ID` (notebook line 851) to UUID. See `dim_tables.sql:12-17`. |
| dim_student             | yes (`02_dimensions_a/dim_student.sql:18`)            | no                                 | one row per (school_id, uid) in both                                        | Two-step UPSERT: `stg_user` then fallback from `stg_student_submission`. No `is_active`/withdrawn filter in either. |
| dim_teacher             | yes (`02_dimensions_a/dim_teacher.sql:12`)            | no                                 | one row per (school_id, uid) in both                                        | Currently EMPTY until `sync_users.py` lands (header comment lines 7–12). Fact rows still resolve `section_instructors` from `stg_student_submission` so this is parity. |
| dim_parent              | yes (`02_dimensions_a/dim_parent.sql:9`)              | no                                 | parity                                                                       | Likewise empty until Phase 7. |
| dim_course              | yes (`02_dimensions_a/dim_course.sql:8`)              | no                                 | parity                                                                       | DISTINCT ON `(school_id, course_nid)`. |
| dim_item                | yes (`03_dimensions_b/dim_item.sql:15`)               | yes (PBIX `dim_item`, 3 758 rows)  | grain match: one row per (school_id, item_id) in both                       | **`item_filter_expression` NOT applied — see §Discrepancies.** |
| dim_question_data       | yes (`04_dimensions_c/dim_question_data.sql:23`)      | yes (PBIX `dim_question_data`)     | one row per (school_id, qkey) in both                                       | Current uses EXACT-equality identifier join; notebook used substring (`Standard.contains(Schoology_Standard)`). Documented & intentional per `pipeline-audit-2026-05-18.md §B1`. |
| dim_standard            | yes (seeded, `supabase/seeds/dim_standard.csv` 7 958) | yes (PBIX `dim_standard`, 7 958)   | row counts match (7 958) — see §Discrepancies for content drift            | Static seed only, never rebuilt (`05_dimensions_d/dim_standard.sql:1-9`). Notebook rebuilt it from a JSON ingest of the live CASE Network API. |
| dim_strand              | yes (`05_dimensions_d/dim_strand.sql:22`)             | yes (PBIX `dim_strand`, 7 071)     | **GRAIN MISMATCH** — see §Discrepancies                                     | Current TRUNCATEs every run and rebuilds from `dim_question_data ⨝ dim_standard` (tenant-local). PBIX `dim_strand` is the full global lookup, 7 071 rows. |
| dim_unit_lesson         | yes (`06_dimensions_e/dim_unit_lesson.sql:7`)         | no                                 | parity                                                                       | (school_id, item_id) DISTINCT. |
| dim_section             | yes (`06_dimensions_e/dim_section.sql:19`)            | no                                 | one row per (school_id, section_nid)                                        | Filters `user_role_id = '286170'` (students only). Notebook builds from `fact_Student_Submissions` (same filter). |
| dim_session             | yes (`06_dimensions_e/dim_session.sql:9`)             | no                                 | (school_id, session_id) — session_id = uuid_2(school_id, session)           | Not a calendar dim — just the school-year token (e.g. `2025-26`). PBIX has no quarter dim either; quarters live as a column on cubes. |
| dim_grade               | yes (`06_dimensions_e/dim_grade.sql:8`)               | no                                 | parity                                                                      | uuid_2(school_id, grade). |
| dim_assessment_type     | yes (`06_dimensions_e/dim_assessment_type.sql:9`)     | no                                 | parity                                                                      | uuid_2(school_id, assessment_type). |
| dim_subject             | yes (`06_dimensions_e/dim_subject.sql:17`)            | yes (PBIX `dim_subject`, 2 034)    | **PBIX excludes 2 hardcoded subject_ids — current does not**                | See §Discrepancies. `show_history_subject` rules ported correctly (Grade 6/7 History remap). `GradeSort` ported. |

PBIX-only / current-only summary:

- PBIX-only dims with NO current equivalent: none. All five PBIX dims have current peers.
- Current-only dims (PBIX has no peer): `dim_school`, `dim_student`, `dim_teacher`, `dim_parent`, `dim_course`, `dim_unit_lesson`, `dim_section`, `dim_session`, `dim_grade`, `dim_assessment_type`. Document only — these feed the fact + cubes upstream of the PBIX model, so absence in PBIX is expected.

---

## What it does (current)

1. **Stage 02 — entity dims** (`dim_course`, `dim_parent`, `dim_school`, `dim_student`, `dim_teacher`) all UPSERT into `(school_id, <entity_id>)` from `stg_student_submission` (students/courses/schools) or `stg_user` (teachers/parents/students rich fields). No active/withdrawn filters, no business deletion masking.
2. **Stage 03 — `dim_item`** (`03_dimensions_b/dim_item.sql:15`). Filters submissions to `user_role_id = '286170'`, computes `Subject_ID = uuid_6(school_id, subject, assessment_type, grade, session, item_name)`, then DISTINCT ON `(school_id, item_id)` keeping the EARLIEST `assessment_date` per partition (matches notebook).
3. **Stage 04 — `dim_question_data`** (`04_dimensions_c/dim_question_data.sql:23`). Joins `stg_question_data` ⨝ `dim_item` for school resolution, then EXACT-EQUALITY joins `standards_val = dim_standard.schoology_standard` to stamp the canonical UUID `identifier`. Dedupe via DISTINCT ON `(school_id, qkey)` preferring non-NULL identifier, longest `schoology_standard` match.
4. **Stage 05 — `dim_standard` + `dim_strand`** (`05_dimensions_d/`). `dim_standard` is a static 7 958-row seed (`supabase/seeds/dim_standard.csv`) loaded once via `supabase/seeds/load_standards.py`. `dim_strand.sql:22` TRUNCATEs and rebuilds from `dim_question_data ⨝ dim_standard ON identifier`, projecting DISTINCT `(identifier, strand)` with surrogate `ROW_NUMBER` id and `strand_id = uuid_2(identifier, strand)`.
5. **Stage 06 — synthetic-key dims** (`dim_session`, `dim_grade`, `dim_subject`, `dim_assessment_type`, `dim_unit_lesson`, `dim_section`). All DISTINCT-ON `(school_id, <synth_id>)` projections from `stg_student_submission` filtered to `user_role_id = '286170'`.

---

## How it does it (current)

- Synthetic IDs use deterministic SHA-256 hashes via `uuid_2`/`uuid_6`/`uuid_8` helpers (`supabase/migrations/20260507000010_uuid_helpers.sql`). Inputs in the order listed at `dim_subject.sql:22-29`, `dim_session.sql:11`, `dim_grade.sql:10`, `dim_assessment_type.sql:13`, `dim_item.sql:39-46`, `dim_question_data.sql:119-128`. These match notebook lines 909–921.
- Standards resolution path:
  1. CSV `Standards_Val` (e.g. `AI.MA.912.AR.1.7` or `MA.912.AR.1.7`) → exact match against `dim_standard.schoology_standard` (`dim_question_data.sql:94-97`).
  2. Picks the row with non-NULL identifier on tie, then longest `matched_schoology_standard` (`dim_question_data.sql:153-155`).
  3. Stamps `dim_question_data.identifier` with the canonical Identifier UUID.
- `dim_strand` then projects `(identifier, strand)` exact-join from `dim_question_data` ⨝ `dim_standard` (`dim_strand.sql:37-45`), so the per-tenant `dim_strand` only contains strands that actually appear in this school's question data.
- Grade-band Grade-9-12 remap and Subject remap occur upstream at the staging layer via `school_grade_overrides` and `subject_overrides` (`stg_student_submission.sql:92`). Dims see the post-remap values.

---

## What legacy did (PBIX dims)

PBIX semantic model contains 5 dims (`02_tables.json:14-18`): `dim_item`, `dim_question_data`, `dim_standard`, `dim_strand`, `dim_subject`. Their build is split:

- **Upstream PySpark notebook** (Schoology_py.ipynb, summarised in `40_schoology_py_spec.md`): produces `dim_*` in Synapse `ldb_dev_s3_schoology_v0p1.dbo` using
  - substring identifier join `df_dim_question_data.Standard.contains(dim_standard.Schoology_Standard)` (notebook line 989, spec line 343),
  - dual-direction union and `dropDuplicates(["Schoology_Standard"])` to rebuild `dim_standard` (spec lines 360–389),
  - `dim_strand.filter(~col("Schoology_Standard").rlike(r"^\d+$"))` to drop pure-numeric codes (spec line 382),
  - `dim_strand` written with `(Identifier, Strand, ID, strand_ID)` shape, PK `ID` from `monotonically_increasing_id` (spec lines 394–406).
- **Power Query (in PBIX)** layer on top (`07_power_query.m`):
  - `dim_item` filters `Item_ID IS NOT NULL AND School_ID = SchoolID AND not Text.Contains(Item_Name, x, OrdinalIgnoreCase)` for every `x` in `Text.Split(FilterExpression, " | ")` — i.e. PBIX strips items whose names contain any of the `FilterExpression` tokens (`07_power_query.m:36-49`).
  - `dim_subject` filters out two specific hardcoded `Subject_ID` hashes: `6dc2c0d6390d497e4cdc75884ba54d44e55af5169563f2a21e80043acff6d2bb` and `639b701aa86164b61a9c0af7ee9af81bbceced349df98c6adbda3d7b2ffd25b2` (`07_power_query.m:60`).
  - `dim_standard` adds an HTML-cleaning step for `description → Custom.CleanedDescription` (`07_power_query.m:122-126`).
  - `dim_strand` filters `strand_ID IS NOT NULL` (`07_power_query.m:80-83`).
- DAX calculated columns on `dim_subject`: `ShowHistorySubject` (Grade 6/7 History remap) and `Grade_no` (`05_dax_columns.dax:1-15`). Both are reproduced in current `dim_subject.sql:37-43`.
- PBIX `dim_strand` head shape: `(Identifier, Strand, strand_ID, ID)`, 7 071 rows (`10_table_heads.json:dim_strand`).
- PBIX `dim_standard` head shape: 7 958 rows, includes `Custom.CleanedDescription`, `cluster`, `Standard_New`, etc. — column-for-column the same set we seeded.

---

## Discrepancies found

### D1 — `dim_subject` is missing the two PBIX hardcoded `Subject_ID` exclusions (HIGH likelihood of affecting Chapter 9 numbers)

PBIX strips two `Subject_ID` hashes (`07_power_query.m:60`):
- `6dc2c0d6390d497e4cdc75884ba54d44e55af5169563f2a21e80043acff6d2bb`
- `639b701aa86164b61a9c0af7ee9af81bbceced349df98c6adbda3d7b2ffd25b2`

Current `dim_subject.sql` has NO equivalent filter. Grepping the repo confirms it: those hashes appear nowhere in `backend/app/transformations/**` or `supabase/migrations/**`. Effect: any item whose `Subject_ID` collides with one of those two hashes is silently included in the current cube, which is denominator drift for **per-subject KPIs**. The hashes are SHA-256 over `(school_id, subject, assessment_type, grade, session, item_name)` so they are tenant-specific — we cannot decode which subject was excluded without the upstream source, but the recipe is reproducible (and was used in the prod PBIX).

Note: even though the relationship in `08_relationships.csv:7` is `dim_item.Subject_ID → dim_subject.Subject_ID` `M:1`, the PBIX engine treats unmatched fact rows as `BLANK` and may exclude them from grouped KPIs depending on the measure. Combined with cross-filtering this is a documented way grades shift by tenths-of-a-percent — exactly the magnitude we see in the Chapter 9 anchor (65.4 vs 66.9).

### D2 — `dim_item` does not honour `schools.item_filter_expression` (HIGH likelihood)

`schools.item_filter_expression` exists (`tenants.sql:13`) but is referenced nowhere in `backend/app/transformations/`. PBIX `dim_item` in M code (`07_power_query.m:36-46`) filters out items whose `Item_Name` contains any token from `FilterExpression` (pipe-delimited substring blocklist).

Effect: current `dim_item` is a superset of PBIX `dim_item`. Items that PBIX hides (e.g. practice tests, retakes, "DO NOT USE" entries) are still flowing into facts and cubes. This is denominator drift for **every aggregate** that joins on `dim_item.Item_ID`, so it propagates straight into the school-level KPI for Chapter 9 (66.9 → 65.4 direction is consistent with extra unfiltered items dragging the average down).

### D3 — `dim_strand` is REBUILT per-tenant from `(identifier, strand)`, PBIX is the GLOBAL 7 071-row seed (MEDIUM likelihood, mostly a labelling effect)

PBIX `dim_strand` is the *global* lookup table — every Identifier/Strand pair in the universe, 7 071 rows (`10_table_heads.json:dim_strand`). The notebook (spec lines 394–406) builds it from the *full* `dim_question_data` corpus across all schools; current builds it from THIS school's `dim_question_data` only (`dim_strand.sql:37-45`).

That alone changes nothing for percentages because both versions emit the same `(identifier → strand)` mapping. BUT note three pitfalls:

1. Current strand build runs AFTER `dim_question_data` is loaded for one tenant. If a question's `standards_val` doesn't exact-match a `schoology_standard` (e.g. legacy text like the `Social Studies` category label noted in `dim_question_data.sql:83-85`), it has `identifier IS NULL` and contributes ZERO `dim_strand` rows. In PBIX the strand is still present in the global table even though no facts join to it.
2. The current `dim_strand.identifier` column may have multiple `(identifier, strand)` pairs for one identifier IF the seed has a `strand` collision. The seed has Identifier `3cc92b67-…-AR.1.7` mapped to exactly one strand (`Algebraic Reasoning`), so the AR.1.7 case is clean. But duplicates are possible and would inflate downstream JOINs.
3. The PBIX-derived `dim_strand.csv` seed itself has 7 071 rows where current's rebuild typically emits only ~10s. Different row counts behind the same logical mapping is harmless for percentage averages but means any DISTINCT count over `dim_strand` (e.g. "strands covered") will diverge.

### D4 — `dim_standard` content drift between PBIX live-rebuild vs static seed (MEDIUM likelihood for AR.1.7 / AR.3.1 drift)

Current loads `supabase/seeds/dim_standard.csv` exactly once (`dim_standard.sql:1-9`). PBIX rebuilds `dim_standard` every notebook run from the live `standards` API (spec lines 358–389) which:

- Dedupes on `Schoology_Standard` (`dropDuplicates(["Schoology_Standard"])`, spec line 383). The seed CSV does **not** dedupe on `schoology_standard`. See in seed: `MA.912.AR.1.7` and `AI.MA.912.AR.1.7` BOTH map to identifier `3cc92b67-…` (verified by grep on the seed file). Same for AR.1.3 → `3cc52b67-…`. **Two seed rows for one logical standard.**
- Filters out pure-numeric `Schoology_Standard` (`filter(~rlike(r"^\d+$"))`, spec line 382). Current seed does not.
- Recomputes `cPalms_Standard = concat_ws('.', slice(split(Schoology_Standard,'\\.'),3,…))` (spec line 384). Current accepts whatever the seed CSV has.

The exact-equality join in `dim_question_data.sql:97` then sees two seed rows for `MA.912.AR.1.7` and `AI.MA.912.AR.1.7` (and the AR.1 cluster too — `MA.912.AR.1` is in the seed for identifier `3cc52b67`). The current dedupe (`dim_question_data.sql:150-155`) chooses one of them deterministically, but the ordering tiebreak (`identifier NULLS LAST, length(matched_schoology_standard) DESC, matched_schoology_standard`) is NOT the same tiebreak PBIX used (PBIX's notebook substring-join + `dropDuplicates(["Schoology_Standard"])` based on the rebuilt standards table). For AR.1.7 the identifier is the same on both seed rows, so the identifier is stable; **but for AR.1.3, current and PBIX could resolve to slightly different rows of `dim_standard` (e.g. with different `cluster`/`Strand` values).** If even one question for Chapter 9 Grade 8 routes to a different `Strand`, the per-standard average shifts by exactly the size of one student's points divided by the denominator — easily ~1 percentage point for AR.1.7 (77.8 vs 78.9). 

### D5 — `dim_strand` PK changed and the legacy `ID` is no longer publish PK (LOW for numbers, schema parity issue)

PBIX `dim_strand.ID` is a Spark `monotonically_increasing_id` and is the publish PK (notebook line 1128, spec line 405). Current uses an auto-generated `dim_strand_pk` BIGINT IDENTITY (`dim_tables.sql:52-58`) because the seed CSV has duplicate `ID` values (see migration `045` lines 47–51). The legacy `ID` is preserved as a non-unique BIGINT, and downstream relations rely on `strand_id` (the SHA-256 hash) anyway, so this does not change percentages. Documented.

### D6 — `dim_question_data.standard` join semantics: exact vs substring (DOCUMENTED, parity intent)

`dim_question_data.sql:71-97` switched from substring (`ILIKE '%' || schoology_standard || '%'`) to **exact equality**. Notebook used `Standard.contains(Schoology_Standard)`. The repo audit (`.hermes/report-parity/pipeline-audit-2026-05-18.md §B1`) argues this is strictly correct because in the staging corpus every `standards_val` exact-matches at least one `schoology_standard`. That is true for this tenant, but **PBIX's report numbers were computed from data ingested by the substring-join Spark pipeline**, so the two pipelines can disagree even when both are "right" — specifically when a `standards_val` like `MA.912.AR.1.3.1` exact-matches nothing in the seed but substring-matches `MA.912.AR.1.3` (cluster code) → would have been stamped with `3cc52b67-…` by PBIX, but is stamped NULL by current. Aggregate counts for the affected strand drop, average for AR.1.3 shifts. Recommend running a probe query to count how many `stg_question_data.standards_val` values currently route to `identifier IS NULL` in `dim_question_data` for the Chapter 9 item.

### D7 — Grade dim normalisation note (LOW)

Legacy spec line 754 reports an `Grade 9-12` -> "Regular 9–12" remap. Current applies it at staging via `school_grade_overrides` (`stg_student_submission.sql:92`). Verified: `dim_grade` projects whatever the staging value is. This is parity, but worth flagging because the previous audit doc (`docs/standards-alignment.md`) describes it as a dim-level fix.

### D8 — Empty `dim_teacher` / `dim_parent` (NONE for KPIs, design)

Both dims are empty until `sync_users.py` lands (`dim_teacher.sql:7-12`, `dim_parent.sql:6-7`). The fact build does not depend on these dims for the contested Chapter 9 numbers — `section_instructors` text lives on `stg_student_submission` → `dim_section` directly. No numeric impact.

---

## Likely numeric impact

Ranking by probability of producing the observed Chapter 9 deltas (legacy 66.9 / 96.1 / 28.9 → current 65.4 / 96.3 / 27.8; AR.1.7 77.8 → 78.9; AR.3.1 69.0 → 69.5):

1. **D2 (`item_filter_expression` not honoured) — MOST LIKELY at the school-level KPI.** Extra items polluting denominators is the canonical way an "average correct %" drops by ~1.5 points (66.9 → 65.4). Easy to confirm: count rows in `dim_item` for the school and compare to the PBIX `dim_item.head.csv` head (3 758 in PBIX vs whatever we have).
2. **D1 (two missing `Subject_ID` exclusions) — second most likely at school level.** Same direction of error, smaller magnitude unless one of the two excluded subjects has many items.
3. **D4 (`dim_standard` seed has un-deduped `schoology_standard` rows; cluster codes like `MA.912.AR.1` co-exist with leaf codes) — most likely for the per-standard AR.1.7 / AR.3.1 deltas.** A single mis-routed question's `identifier` flips the numerator of one cluster's average. The audit doc (`dim_question_data.sql:74-89`) explicitly calls out that prefix collisions could mis-stamp identifiers; the fix (exact-equality + length tiebreak) is logically sound, but the seed has not been deduped to PBIX's `dropDuplicates(["Schoology_Standard"])` rule, so the input space differs from PBIX's. Confirming probe: 

   ```sql
   -- Are any (schoology_standard) values duplicated in the seed?
   SELECT schoology_standard, count(*) FROM dim_standard
   GROUP BY 1 HAVING count(*) > 1 ORDER BY 2 DESC LIMIT 20;
   -- Are any pure-numeric schoology_standards present (PBIX would drop them)?
   SELECT count(*) FROM dim_standard WHERE schoology_standard ~ '^\d+$';
   ```

4. **D6 (exact-equality vs substring join) — secondary contributor to per-standard deltas.** Any `standards_val` like `MA.912.AR.1.3.1` (sub-leaf) that PBIX folded into `AR.1.3` via substring is currently NULL — that question is silently dropped from AR.1.3's denominator. Probe:

   ```sql
   SELECT count(*) FROM dim_question_data
   WHERE standards_val IS NOT NULL AND identifier IS NULL
     AND item_id = '8359960427';
   ```

5. **D3 (`dim_strand` rebuilt per-tenant) — neutral for percentages, breaks `count distinct strand` numbers.** Not the Chapter 9 culprit, but worth aligning if a Strand Summary report wants a stable global denominator.

6. **D5, D7, D8 — schema/empty-table parity only, no numeric impact.**

### Recommended verification queries (one-shot, read-only)

```sql
-- D1 probe — are the two PBIX-excluded Subject_IDs present in current?
SELECT subject_id, school_id, subject, grade, item_name
FROM dim_subject
WHERE subject_id IN (
  '6dc2c0d6390d497e4cdc75884ba54d44e55af5169563f2a21e80043acff6d2bb',
  '639b701aa86164b61a9c0af7ee9af81bbceced349df98c6adbda3d7b2ffd25b2'
);

-- D2 probe — what is item_filter_expression set to, and how many dim_item rows
-- would PBIX drop?
SELECT s.school_id, s.name, s.item_filter_expression,
       count(*) FILTER (
         WHERE EXISTS (
           SELECT 1 FROM regexp_split_to_table(s.item_filter_expression, ' \| ') tok
           WHERE i.item_name ILIKE '%' || tok || '%'
         )
       ) AS items_pbix_would_drop,
       count(*) AS items_total
FROM schools s
JOIN dim_item i ON i.school_id = s.school_id
GROUP BY s.school_id, s.name, s.item_filter_expression;

-- D4 probe — duplicated schoology_standard codes for AR.1.x
SELECT schoology_standard, identifier, strand
FROM dim_standard
WHERE schoology_standard LIKE '%AR.1.%' OR schoology_standard LIKE '%AR.3.%'
ORDER BY schoology_standard, identifier;

-- D6 probe — questions whose standards_val did NOT exact-match (would have
-- substring-matched in PBIX)
SELECT standards_val, count(*)
FROM dim_question_data
WHERE standards_val IS NOT NULL AND identifier IS NULL
GROUP BY 1 ORDER BY 2 DESC LIMIT 50;
```

These four probes will rank the four candidate explanations definitively against the live data.
