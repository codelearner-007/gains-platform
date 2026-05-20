# 03 — Staging Audit

Scope: how parsed in-memory rows land in `stg_*` tables. Type coercions, deduplication, filter conditions, null handling. Parsing (track 2) and dim joins (track 4) are NOT audited here.

Anchor: Chapter 9 Test, Grade 8, item `8359960427`. Legacy 66.9 / 96.1 / 28.9 vs new 65.4 / 96.3 / 27.8.

---

## What it does (current)

Five staging models live under `backend/app/transformations/01_staging/`. The orchestrator runs them in order before any dim/fact build:

`backend/app/transformations/runner.py:53-59`
```
("01_staging/stg_user.sql",                "staging"),
("01_staging/stg_question_data.sql",       "staging"),
("01_staging/stg_student_submission.sql",  "staging"),
("01_staging/stg_submission_summary.sql",  "staging"),
("01_staging/stg_standard.sql",            "staging"),
```

Each file is `TRUNCATE` + `INSERT … SELECT FROM raw_*` (`backend/app/transformations/runner.py:233-243`). Tenant overrides (subject, course→subject, grade, teacher-pair) are joined here so downstream dims never see raw values. `stg_standard` is a deliberate no-op because `dim_standard` is a globally seeded table loaded once by `supabase/seeds/load_standards.py` (`backend/app/transformations/01_staging/stg_standard.sql:1-12`).

Per-table responsibilities:

| Stg file | Source raw | What staging adds |
|---|---|---|
| `stg_user.sql` | `raw_user` | `TRIM` + `NULLIF '' → NULL`, resolves `schoology_school_id` from `schools` (`stg_user.sql:47`). No filters. |
| `stg_question_data.sql` | `raw_question_data` | `TRIM` + `NULLIF '' → NULL`, applies `subject_overrides` + `school_grade_overrides`. No `subject_course_overrides` (no `course_name` column in question-data). |
| `stg_student_submission.sql` | `raw_student_submission` | `TRIM` + `NULLIF '' → NULL`, applies all four overrides (subject, subject-by-course-regex, grade, teacher-pair). |
| `stg_submission_summary.sql` | `raw_submission_summary` | `TRIM` + `NULLIF '' → NULL`. No overrides. |
| `stg_standard.sql` | n/a | `SELECT 1;` — intentional no-op. |

Stage-table DDL: `supabase/migrations/20260507000095_stage_tables.sql:17-149`. Raw-table DDL: `supabase/migrations/20260507000040_raw_tables.sql`.

---

## How it does it (current)

Five mechanical patterns dominate every stg_* SELECT:

1. `NULLIF(TRIM(rss.col), '')` — coerce blank strings to NULL on every TEXT column. Numeric/date columns are passed straight through (they were already typed at parse time — see `backend/app/jobs/parsers/common.py:99-220`).
2. **No row filtering.** Every `INSERT … SELECT` is a 1:1 projection of `raw_*` joined to `schools` — there are no `WHERE` clauses that drop rows.
3. **No dedupe.** No `ROW_NUMBER`/`DISTINCT`/`ON CONFLICT` — the uniqueness constraint lives upstream on `raw_*(school_id, source_file_hash, unique_key)` (`supabase/migrations/20260507000040_raw_tables.sql:19,70,110,146`).
4. **Override precedence** (mirroring spec §3 lines 232-413):
   * Subject in `stg_student_submission`: `subject_course_overrides` regex wins over `subject_overrides` grade+exact match (`stg_student_submission.sql:68`).
   * Grade: `school_grade_overrides` wins via lateral first-match-by-override_id (`stg_student_submission.sql:89-97`).
   * Section instructors: `teacher_pair_overrides.primary_teacher` wins over raw `section_instructors` (`stg_student_submission.sql:42-43,98-100`).
5. **Truncation** (`Question`, `Answer Submission` → 7500 chars) happens upstream in the parser, NOT in staging (`backend/app/jobs/parsers/common.py:154-160`).

Insertion driver is `app.transformations.runner._exec_statements` (`runner.py:300-309`) using SQLAlchemy `text(stmt)` per statement; rows go straight from `raw_*` to `stg_*` inside the orchestrator's transaction.

---

## What legacy did (PBIX / Power-Query M / Schoology_py notebook)

The `.pbix` Power Query M is a thin pass-through — it only `Sql.Database`-reads already-built Synapse tables (`data/_pbix_extract/07_power_query.m:1-204`). The real "staging" lives in `Schoology_py.ipynb`'s `preprocess_schoology_dataset` (cell-2 lines ~440-606) and `build_fact_tables` (cell-2 lines 1164-1186). Legacy staging differs in several substantive ways:

### A. Question-Data Standards group-filter (cell-2 lines 514-518)

```python
standards_group_counts = df_melt1.groupby('Question_ID')['Standards_Val'].transform(lambda x: x.notna().sum())
df_melt1 = df_melt1[
    ~((df_melt1['Standards_Val'].isna() | (df_melt1['Standards_Val'] == '')) & (standards_group_counts > 0))
]
```

Legacy drops every `(Question_ID, Standards_Val=NULL)` row whose Question_ID has **any other** non-null Standards_Val row in the same file. Current parser approximates this row-by-row at parse time (`backend/app/jobs/parsers/question_data.py:107-111`) — equivalent for the typical Athenian shape (one source row per Question_ID with 0–4 melted Standards), but diverges if a Question_ID legitimately appears twice in the same file with different Standards counts.

### B. Latest-rundate window dedupe before the fact build (cell-2 lines 1170-1180)

```python
key_columns = [c for c in df_Student_Submissions.columns
               if c not in ("rundate","Unique_Key","Points_Received","Submission_Grade")]
w = Window.partitionBy(key_columns).orderBy(F.col("rundate").desc())
df_Student_Submissions = (df_Student_Submissions
    .withColumn("rn", F.row_number().over(w))
    .filter("rn = 1").drop("rn"))
```

Legacy keeps the **latest** row per (all-key-cols-except points/grade), ordered by `rundate DESC`. This means re-attempts and re-uploads collapse to a single row — but the **kept row's Points_Received and Submission_Grade are the latest** values. There is no equivalent dedupe in `stg_student_submission.sql` or in any downstream file before `fact_student_submission.sql`. The Postgres pipeline relies on the raw-table `UNIQUE (school_id, source_file_hash, unique_key)` plus the parser's `unique_key` formula (`backend/app/jobs/unique_key.py`) — but `unique_key` for student_submissions is `User_UID + Item_ID + Question_ID + Position_Number + Answer_Submission + Points_Received + Points_Possible + Submission + Correct_Answer` (notebook line 593), so two rows with **the same answer but different scores in re-uploads** survive into stg_ in the new pipeline but are collapsed by legacy.

### C. Question-Data filter applied at fact build (cell-2 line 1186)

```python
df_Question = df_Question.filter(
    (F.col('Standards_Val').isNull()) & (F.col('Standards') != 'Standards17')
    | (F.col('Standards').isNull() & F.col('Standards_Val').isNull()))
```

Legacy further drops a swath of question_data rows just before joining to fact (it keeps only rows where Standards_Val is null AND Standards != 'Standards17', or both columns are null). The current pipeline preserves `standards_val` in `stg_question_data` regardless of which of the four melted source columns produced it; no `Standards != 'Standards17'` exclusion exists. This is a candidate cause for differing question populations in cube aggregations.

### D. Type coercion: legacy is string-typed end-to-end

`data/_pbix_extract/03_schema.csv` shows the PBIX tabular model imports `fact_student_submission.Points_Received`, `Points_Possible`, `Total_Points`, `Submission`, `Submission_Grade`, `First_Access`, `Latest_Attempt`, `Total_Time` all as **`string`** (lines 65-93 of the schema CSV). All numeric coercion in legacy happens **inside DAX measures** at query time (e.g., `SUM(Points_Received)` implicitly casts). The current Postgres pipeline coerces at parse time (`backend/app/jobs/parsers/common.py:99-142`) and stores as `NUMERIC(10,4)` / `INTEGER` (`supabase/migrations/20260507000095_stage_tables.sql:39,49-50,71,77-83,109,111`). NUMERIC(10,4) **silently truncates** anything beyond 4 decimal places — but Schoology values are already in 0.00–1.00 or 0.0–N.0 range, so this is unlikely to be the smoking gun.

### E. CSV encoding

Legacy pre-landing reads CSVs as **ISO-8859-1** with `quoteAll=true` (notebook line 474 / spec §3 lines 142-153). Current parser decodes as **utf-8-sig** (`backend/app/jobs/parsers/common.py:60`). For Athenian CSVs this is normally identical, but any high-bit Windows-1252 character (smart quotes, en-dash, copyright) parses to different bytes between the two. Items with diacritics or special punctuation in `item_name` / `question` could collide differently in unique-key computation.

### F. No tenant overrides in legacy staging

Legacy applied subject/grade/teacher overrides inside `preprocess_schoology_dataset` (notebook lines 232-413) — already-overridden values landed in stage2. The Postgres pipeline stores raw values in `raw_*` and applies overrides at **staging** time via lateral joins (`stg_student_submission.sql:68-100`). Same end result for Athenian provided the override seed tables match the hardcoded notebook dicts.

---

## Discrepancies found

### Column-by-column: stg_student_submission vs legacy student_submissions

| Column | Current type | Legacy type (Spark/PBIX) | Difference |
|---|---|---|---|
| `points_received` | `NUMERIC(10,4)` | `string` (cast on aggregate in DAX) | Type mismatch; truncation at 4 dp. |
| `points_possible` | `NUMERIC(10,4)` | `string` | Same. |
| `submission` | `INTEGER` | `string` | `coerce_int("5.0")` warns + casts; legacy keeps the original literal. |
| `submission_grade` | `NUMERIC(10,4)` | `string` | Same. |
| `total_time` | `INTERVAL` | `string` "HH:MM:SS" | Legacy parses `Total_Time` at cube time (`int(split(t,':')[0])*3600+…`). Current converts at parse time. |
| `first_access`, `latest_attempt` | `TIMESTAMPTZ` (assumed UTC) | naive string | Legacy never normalises TZ; current force-stamps UTC (`coerce_timestamp` in `common.py:175-199`). |
| `subject` | `TEXT` (override resolved) | `string` (override resolved at pre-landing) | Behaviour equivalent if seed tables match notebook hardcoded dicts. |
| `grade` | `TEXT` (override resolved) | `string` (override resolved at pre-landing) | Same. Grade "9–12" en-dash sensitive. |
| `section_instructors` | `TEXT` (teacher-pair resolved) | `string` (resolved by legacy `replace_values` UDF) | Same. |
| `(no col)` | n/a | `rundate` (used for dedupe) | **Legacy uses `rundate` to dedupe**; current pipeline relies on raw `unique_key` only. |
| `(no col)` | n/a | `Unique_Key` (kept in stage2) | Current keeps `unique_key` on `raw_*` only — not propagated to `stg_*`. |

### Column-by-column: stg_question_data vs legacy question_data

| Column | Current type | Legacy type | Difference |
|---|---|---|---|
| `standards_val` | `TEXT` | `string` | Same. Current parser drops empty Standards within a row if at least one non-empty value exists. Legacy drops at GROUP-BY-Question_ID level. Equivalent for one-source-row-per-question files. |
| `total_points`, `correctly_answered`, `most/least/average_points_earned` | `NUMERIC(10,4)` | `string` | Same shape issue as fact table. |
| `answer_breakdown_count` | `INTEGER` | `string` | Type-coercion at parse time. |
| `answer_breakdown_pct` | `NUMERIC(10,4)` | `string` | Same. |
| `question_no` | `TEXT` (scipy `rankdata(method='dense')` reimplemented at parse) | `int` | Current stores as TEXT — matches schema CSV (`question_no,string`) but is now a numerically-sortable string rather than a real int. |

### Filter / null-handling differences (highest impact)

1. **No latest-rundate dedupe on student-submissions.** If Athenian re-uploaded any Item-Question-Student combination between original ingest and a re-export with corrected scores (a common scenario for late-graders), legacy keeps only the latest score; current keeps both rows under the raw `unique_key` constraint. This **inflates the denominator** of any sum/avg that groups by `(Item_ID, Question_ID, User_UID)` and produces a per-row average — which is exactly the shape of `cube_grade_summary`. **This is a strong candidate for the 66.9 → 65.4 KPI drift.**
2. **No `Standards != 'Standards17'` exclusion on question_data.** Legacy excludes any Standards17-melted rows before computing per-question stats; current keeps every emitted melt row. If a Question_ID has both an in-scope Standards row and a Standards17 row, fact_student_submission may join on the wrong one.
3. **NUMERIC truncation** at 4 dp on points columns is harmless for Schoology data (values are 0.0/0.5/1.0/2.0), but it is a real type difference.
4. **No `unique_key` column** on stg_student_submission, so any downstream re-dedupe lacks the natural key the notebook used.

### Deduplication keys

| Layer | Current key | Legacy key |
|---|---|---|
| Raw insert | `UNIQUE (school_id, source_file_hash, unique_key)` (`raw_tables.sql:19,70,110,146`). `unique_key` matches notebook formulae. | None at ingest — `oea.upsert` MERGE on PK (e.g., `User_id_ques_id_stand` for fact). |
| Staging | None (1:1 pass-through). | `groupby(Question_ID).Standards_Val.notna().sum() > 0` filter (Q-data) — see cell-2 line 514. |
| Pre-fact | None. | `row_number over (all cols − rundate − Unique_Key − Points_Received − Submission_Grade) ORDER BY rundate DESC` (cell-2 lines 1170-1180). |

### Submission-summary semantics

Both sides emit **one row per (student × question_label)** — confirmed in `backend/app/jobs/parsers/submission_summary.py:71-98` and spec §3 line 168. `unique_key = Schoology_ID + Question_label`. So a student's overall `submission_score` is duplicated across every question row. Any naive `AVG(submission_score)` on `stg_submission_summary` would over-count by the question count. Not yet a discrepancy because no downstream model aggregates submission_summary at the staging level — but this is a footgun.

### Standard normalization

`stg_standard` is a no-op (`stg_standard.sql:12`); the seeded `dim_standard` is loaded once via `supabase/seeds/load_standards.py` from `supabase/seeds/dim_standard.csv`. Legacy `dim_standard` is JOIN-built dynamically (notebook lines 988-1097) and includes a `cPalms_Standard` derived column. The current `dim_standard` seed must already contain the equivalent of `cPalms_Standard`, otherwise downstream filters that match on cPalms-trimmed standards will mismatch. Confirm seed-file columns versus notebook line 1085 derivation (`concat_ws('.', slice(split(Schoology_Standard, '.'), 3, …))`).

### Computed columns

Legacy DAX-computed columns visible in `data/_pbix_extract/05_dax_columns.dax`:

- `cube_question_summary_overall[Sorting Question_No] = INT(Question_No)` — confirms `Question_No` is string in the model and gets cast at presentation time. Current stores `question_no` as TEXT in `stg_question_data` — matches.
- `cube_question_summary_overall[Trimmed_Standard]` — DAX-side derivation of the cPalms trim. None of this happens in staging in either system, but legacy's `dim_standard.cPalms_Standard` column is the materialised version (notebook line 1085). Need to confirm the seed has it.
- `dim_subject[ShowHistorySubject]`, `dim_subject[Grade_no]` — DAX presentation columns; not staging concerns.

### Type coercions specific to the KPI drift

Schoology submission scores in CSVs are **fractions in [0,1]** (e.g., `0.5` for half credit). The legacy pipeline keeps them as strings up through the fact then `SUM/SUM` in DAX. Current pipeline coerces to `NUMERIC(10,4)`. Both should produce identical aggregates as long as nothing converts to integer or to 0–100 percentage early.

Searches for percentage handling in staging surface nothing — neither `stg_question_data.correctly_answered` nor `stg_student_submission.points_received` is multiplied by 100 anywhere in the staging SQL. So the 0–1 vs 0–100 mixup is **not** at the staging layer in the current code; if it exists it would be in cube SQL (track 5).

---

## Likely numeric impact

Ranked by suspected magnitude for the Chapter 9 / item 8359960427 / Grade 8 discrepancy:

1. **Missing latest-rundate dedupe of student_submissions** (no equivalent of notebook cell-2 lines 1170-1180). On a single fresh ingest this is a no-op. On any re-ingest of the same Item with corrected scores, current pipeline retains both submissions and legacy retains only the latest. **High-impact suspect for the 66.9 → 65.4 drift if the dataset has any re-graded rows.**
2. **Missing `Standards != 'Standards17'` exclusion on question_data before fact join** (notebook cell-2 line 1186). Causes extra rows to participate in per-question rollups — could shift `cube_question_summary` numerators downward (more rows averaged in). Plausible explanation for the question-level 96.1 → 96.3 movement.
3. **`stg_standard` no-op** versus legacy's dynamic rebuild + `cPalms_Standard` derivation. If the seeded `dim_standard.csv` is missing `cPalms_Standard` or has a different `Schoology_Standard` cardinality, downstream substring joins `Standard LIKE '%' || Schoology_Standard || '%'` will miss/match differently. Smaller numeric impact unless the standards population differs at the school.
4. **NUMERIC(10,4) silent truncation.** Negligible at Schoology score granularity.
5. **CSV encoding utf-8 vs ISO-8859-1.** Negligible unless item names / questions contain Windows-1252 specials.
6. **TIMESTAMPTZ stamping** for `first_access`/`latest_attempt`. Affects only date-based filters in the report, not the KPI numerator.

The first two items are the only ones plausible enough to explain a ~1.5-point KPI drift on a single item. Confirm by:

- Counting `raw_student_submission` rows for `(school_id, item_id='8359960427')` and grouping by the legacy-equivalent dedupe key; if duplicates exist, item #1 is your culprit.
- Counting `stg_question_data` rows for that `item_id` and checking how many would be filtered by `Standards != 'Standards17'` — any non-zero count moves the needle.
