# 05 — Facts Audit

Anchor: Chapter 9 Test, Grade 8, item_id `8359960427` (legacy 66.9 / 96.1 / 28.9 vs new 65.4 / 96.3 / 27.8).
Scope: `backend/app/transformations/07_facts/` + `backend/app/transformations/08_hash/` and their DDL.
Sources read:
- `backend/app/transformations/07_facts/fact_student_submission.sql`
- `backend/app/transformations/08_hash/{dim_section_hash,dim_student_hash,fact_student_submissions_hash}.sql`
- `backend/app/transformations/runner.py`
- `supabase/migrations/20260507000060_fact_table.sql` + `…_080_hash_tables.sql`
- `data/_pbix_extract/02_tables.json`, `03_schema.csv`, `05_dax_columns.dax`, `06_dax_tables.csv`, `07_power_query.m`, `08_relationships.csv`, `09_statistics.csv`, `10_table_heads.json`
- `gains legacy/.../Schoology_py.ipynb` (`build_fact_tables`, lines 1180–1294, and the `build_pseudomyzed_tables` block at lines 1295–1320)

---

## What it does (current)

`fact_student_submission` is one INSERT … ON CONFLICT DO UPDATE built from `stg_student_submission`.

Pipeline order (`runner.py:53-100`):

```
staging → dimensions (a..e) → facts → hash → cubes
```

Run mode: facts is **append-with-upsert** (no TRUNCATE on the fact table itself); hash tables and cubes are TRUNCATE + INSERT.

DDL (`supabase/migrations/20260507000060_fact_table.sql:7-50`): 35 columns, PK = `user_id_ques_id_stand TEXT`. Indexed on `(school_id)`, `(school_id, item_id)`, `(school_id, question_id)`, `(school_id, user_uid)`, `(school_id, subject_id)`, `(identifier)`.

## How it does it (current)

`backend/app/transformations/07_facts/fact_student_submission.sql`:

1. **Filter** `WHERE src.user_role_id = '286170'` (students only) — `fact_student_submission.sql:119`.
2. **Dedupe** `ROW_NUMBER() OVER (PARTITION BY school_id, user_uid, question_id, position_number, answer_submission ORDER BY submission DESC NULLS LAST, points_received DESC NULLS LAST, points_possible DESC NULLS LAST)` and keep `rn=1` — `fact_student_submission.sql:121-135, 179`.
3. **Join 1 (LEFT)** `dim_question_data` distinct-on `(question_id, standard)` → `qd.standard` — `fact_student_submission.sql:136-150`.
4. **Join 2 (LEFT LATERAL)** `dim_standard` on exact `schoology_standard = qd.standard`, `ORDER BY identifier LIMIT 1` (pin to lex-smallest identifier) — `fact_student_submission.sql:168-176`.
5. **Join 3 (LEFT)** `dim_strand` on `identifier` — `fact_student_submission.sql:177-178`.
6. **Final dedupe** `DISTINCT ON (9-part key)` adding `std` (Standard text) to the legacy 8-part key — `fact_student_submission.sql:181-219`.
7. **Compute** derived columns on the SELECT: `user_id_ques_id_stand`, `user_name = trim(first_name||' '||last_name)`, `user_id_ques_id = user_uid||'-'||question_id`, `grade_id = uuid_2(school_id, grade)`, `assessment_id = uuid_2(school_id, assessment_type)`, `subject_id = uuid_6(school_id, subject, assessment_type, grade, session, item_name)` — `fact_student_submission.sql:222-278`.
8. **Upsert** `ON CONFLICT (user_id_ques_id_stand) DO UPDATE` — `fact_student_submission.sql:280-315`.

Hash tables (`08_hash/`) are pure projections off the fact:
- `dim_student_hash` — `TRUNCATE`, label = `'Student_Name '||(ROW_NUMBER() OVER (PARTITION BY school_id ORDER BY user_uid) - 1)` (`dim_student_hash.sql:12-37`). Note source is `DISTINCT ON (school_id, user_uid)` of fact, NOT legacy's `groupBy(User_UID, User_Name).agg(sum(Item_ID))`.
- `dim_section_hash` — `TRUNCATE`, label = `'Teacher_Name '||(ROW_NUMBER() OVER (PARTITION BY school_id ORDER BY section_nid, COALESCE(section_instructors,''))) - 1)` (`dim_section_hash.sql:13-35`). Source: `dim_section` (not the fact).
- `fact_student_submissions_hash` — `TRUNCATE` then `SELECT … LEFT JOIN dim_student_hash` (`fact_student_submissions_hash.sql:12-96`). user_name replaced by hash; the extra `student_name_hash` column also written.

## What legacy did (PBIX facts + DAX columns)

PBIX `fact_student_submission` is **empty** in the published model: `09_statistics.csv` reports cardinality=1 for every column (line 188-222), and `10_table_heads.json` reports `rows: 0` for `fact_student_submission`. Power Query M (`07_power_query.m:105-112`) just imports the row dump from Synapse view `dbo.fact_student_submission`; it adds no transformations. `05_dax_columns.dax` defines **zero** DAX calculated columns on `fact_student_submission`, and `06_dax_tables.csv` is empty (no DAX-defined fact). Consequence:

> There is no `IsCorrect`, `Score%`, `IsAttempted`, `IsMostRecentAttempt`, or `WeightedScore` on the PBIX fact. All correctness math is done upstream in the cubes (cube_question_summary, cube_grade_summary, …). The fact's only role in PBIX is M:M relationship plumbing — `08_relationships.csv:10,15` shows two M:M edges from `fact_student_submission` to `cube_questionincorrectchoice_summary` only.

The actual fact build that produces the row dump consumed by PBIX is the legacy Spark notebook `Schoology_py.ipynb` `build_fact_tables` (lines 1180-1294). Key steps:

```python
# notebook 1184-1196
df_Student_Submissions = oea.load('stage2/Ingested/schoology/v.../student_submissions')
df_Student_Submissions = df_Student_Submissions.withColumn("rundate", F.to_date("rundate", "yyyy-MM-dd"))
key_columns = [c for c in df_Student_Submissions.columns
        if c not in ("rundate", "Unique_Key", "Points_Received", "Submission_Grade")]
w = Window.partitionBy(key_columns).orderBy(F.col("rundate").desc())
df_Student_Submissions = (
        df_Student_Submissions
            .withColumn("rn", F.row_number().over(w))
            .filter("rn = 1")
            .drop("rn")
)
```

- No `User_Role_ID` filter anywhere in `build_fact_tables` — the role filter only exists in `build_dim_tables` (`Schoology_py.ipynb:863, 878, 888`) when carving `dim_student` / `dim_teacher` / `dim_parent`. The fact carries every role.
- Standard join is a plain `LEFT JOIN dim_standard ON Standard` (`Schoology_py.ipynb:1252-1262`); if two `Identifier` rows share the same `Schoology_Standard` text, **legacy fans the fact out** and lets the publish step's `primary_key='User_id_ques_id_stand'` (8-part, including Standard but NOT Identifier) overwrite — last write wins, which in Spark is non-deterministic.
- Persistence is `delete_stale_rows(...)` + `publish(...)` (`Schoology_py.ipynb:1291-1292`), i.e. **rows present in the old snapshot but not in the new build are removed**. Equivalent to `TRUNCATE + INSERT` for steady-state behaviour.
- Pseudonymisation tables (`Schoology_py.ipynb:1297-1320`):

  ```python
  # dim_section_Hash
  fact_student_submissions_Unique = fact_student_submissions.groupby("Section_NID","Section_Instructors").agg(sum("Item_ID"))
  fact_student_submissions_Unique = fact_student_submissions_Unique.select("Section_NID","Section_Instructors") \
       .withColumn("TeacherName_Hash", concat(F.lit("Teacher_Name "), monotonically_increasing_id()))

  # dim_student_hash
  fact_student_submissions_Unique = fact_student_submissions.groupby("User_UID","User_Name").agg(sum("Item_ID"))
  fact_student_submissions_Unique = fact_student_submissions_Unique.select("User_UID","User_Name") \
       .withColumn("StudentName_Hash", concat(F.lit("Student_Name "), monotonically_increasing_id()))
  ```

  Legacy uses `monotonically_increasing_id()` — a **non-deterministic, partition-dependent counter** with no PARTITION BY school_id. Current uses `ROW_NUMBER() OVER (PARTITION BY school_id ORDER BY user_uid)`. Numbers differ; that does not affect KPI math but does change which "Student_Name N" label maps to which actual student. Not a numeric driver.

## Discrepancies found

### D-FACT-1 — Role filter present in current, absent in legacy

`fact_student_submission.sql:119` adds `WHERE src.user_role_id = '286170'`. Legacy `build_fact_tables` (`Schoology_py.ipynb:1180-1294`) never filters `User_Role_ID`. The stg_student_submission staging file's own comment (`stg_student_submission.sql:13`) acknowledges "The notebook applies role-id filtering AT DIM TIME, NOT here".

**Why this differs from the spec the current file claims to follow.** The fact's header comment (`fact_student_submission.sql:7-8`) cites "notebook line 1199" as the source of the filter. Line 1199 in the legacy notebook is a column-rename (`User_School_ID → School_ID`), not a role filter. The filter is incorrectly attributed.

**Numeric impact direction.** If raw CSV rows include non-student `User_Role_ID` values that nonetheless have valid `Submission`/`Points_Received` data, current pipeline **drops them** but legacy keeps them. For an 18-question 27-student assessment the population is overwhelmingly students, so the row delta is likely small (0-2 stray rows). But if the source export contains a teacher submission row with `points_received` populated, that row will appear in legacy averages and disappear in current → small KPI nudge.

### D-FACT-2 — Pre-INSERT dedupe partition is far narrower than legacy

`fact_student_submission.sql:127-133`:

```sql
ROW_NUMBER() OVER (
    PARTITION BY school_id, user_uid, question_id, position_number, answer_submission
    ORDER BY submission DESC NULLS LAST,
             points_received DESC NULLS LAST,
             points_possible DESC NULLS LAST
)
```

Legacy (`Schoology_py.ipynb:1186-1196`) partitions by **every column except `(rundate, Unique_Key, Points_Received, Submission_Grade)`** — i.e. ~24 columns including `Submission`, `Points_Possible`, `Item_ID`, `Item_Name`, `Section_Code`, `Section_NID`, `First_Access`, `Latest_Attempt`, `Total_Time`, `Session`, `Assessment_type`, `Subject`, `Grade`, `Section`, `File_Name`, `Sub-Question`, `Correct_Answer`. Order is `rundate DESC`.

Concrete behavioural delta:

| Scenario | Legacy | Current |
| --- | --- | --- |
| Same (student, question, position, answer) submitted on two ingest dates, identical scores | One row, latest rundate | One row (correct ordering by submission desc) |
| Same (student, question, position, answer) but **different `Submission` numbers** (i.e. 1st vs 2nd attempt) | **Two rows kept** (Submission in partition) | **One row** — current collapses across Submission |
| Same (student, question, position, answer, points_possible) but `points_received` differs across ingests | Two rows if `Submission_Grade` differs (Submission_Grade NOT in partition for legacy → keeps once), else collapsed | One row, max points_received wins |
| Same (student, question, position) but the student changed their answer (answer_submission differs) | Both kept | Both kept |

Net effect: current produces **strictly fewer or equal** rows than legacy for the same input. For an item where any student took multiple attempts, current under-counts. The "27 × 18 = 486" naive expectation assumes one attempt per student; if legacy carried a small number of re-attempt rows the legacy average would shift by the typical magnitude observed (~1pt).

The ordering choice also matters: current picks `submission DESC` (i.e. highest-numbered attempt — usually "most recent") which is reasonable, but legacy's rundate-desc isn't equivalent. They will tie only when the two attempts arrive in monotonic rundate order.

### D-FACT-3 — Standard join fanout collapsed by LATERAL pin

`fact_student_submission.sql:168-176`:

```sql
LEFT JOIN LATERAL (
  SELECT identifier
  FROM dim_standard
  WHERE schoology_standard = qd.standard
  ORDER BY identifier
  LIMIT 1
) ds ON TRUE
```

Legacy (`Schoology_py.ipynb:1257-1262`):

```python
fact_Student_Submissions = fact_Student_Submissions.join(dim_standard, on=["Standard"], how="left")
```

When the seed `dim_standard.csv` has two `Identifier` rows with the same `Schoology_Standard` text (the file header comment at `fact_student_submission.sql:160-167` calls these out — `3cd52b67…` vs `3cdd2b67…` both mapping `MA.912.AR.3.1`), legacy **fans out** the fact (one row per identifier), then publish overwrites on its 8-part PK (which uses `Standard` text, not `Identifier`). Last write wins — non-deterministic in Spark.

Current pins identifier to lex-smallest deterministically, then includes `std` in the 9-part PK so distinct standard aliases sharing an identifier survive. This is a genuine improvement, but it changes the row that wins for any standard with multi-identifier pollution. If the anchor item's standard has such pollution, the joined `identifier`/`strand_id` will be a different UUID than what legacy emitted into the cubes — which can flip which cube `identifier` bucket the row contributes to. Downstream standard-summary KPIs will differ even if `fact_student_submission` row counts are identical.

### D-FACT-4 — Final dedupe key extended from 8-part to 9-part

`fact_student_submission.sql:189-219` adds `std` (Standard text) to the legacy 8-part PK. Legacy PK (notebook line 1271-1289) is exactly the 8 columns: school_id, user_uid, question_id, position_number, answer_submission, points_possible, submission, **Standard** (text, NOT identifier).

Look closely: legacy already had `Standard` in the PK. Current adds `std` AND keeps `ident` in the key. The current key effectively becomes `(8 legacy parts) + COALESCE(ident, 'DEFAULT_STANDARD')`. That is **more permissive** — when the legacy PK would have collapsed two rows with the same Standard text but different Identifier (caused by the dim_standard pollution called out in D-FACT-3), current keeps both rows.

Net effect: current fact carries strictly **more rows** than legacy where identifier-fanout occurs, but strictly **fewer** rows than legacy where multi-attempt rows existed (D-FACT-2). The two effects can offset partially.

### D-FACT-5 — No TRUNCATE on the fact table

`fact_student_submission.sql:48` is `INSERT ... ON CONFLICT DO UPDATE`, no preceding `TRUNCATE TABLE fact_student_submission;`. Re-running the pipeline keeps **stale rows** from prior runs whose source PK no longer exists. Legacy uses `delete_stale_rows + publish` (`Schoology_py.ipynb:1291-1292`) which deletes stale rows.

This is a divergence in steady-state semantics, not in a single-shot first-run computation. On a clean DB the first run matches legacy, but any subsequent re-run with source data trimmed (deleted CSV rows) will have current carrying ghost rows that legacy wouldn't.

### D-FACT-6 — Hash dimension grain differs from legacy

Legacy `dim_student_Hash` (`Schoology_py.ipynb:1307-1310`):

```python
fact_student_submissions_Unique = fact_student_submissions.groupby("User_UID","User_Name").agg(sum("Item_ID"))
fact_student_submissions_Unique.select("User_UID","User_Name").withColumn(
    "StudentName_Hash", concat(F.lit("Student_Name "), monotonically_increasing_id())
)
```

Legacy grain is `(User_UID, User_Name)` — if one student appears with two different `User_Name` values (e.g. data drift in first/last name), legacy emits two rows for the same `User_UID`, breaking the implicit PK assumption.

Current (`dim_student_hash.sql:30`) uses `DISTINCT ON (school_id, user_uid)` and orders by `(school_id, user_uid, user_name)` — exactly one row per `user_uid`. Numeric impact: none on KPIs, but the hash labels assigned differ. Also the school_id partition in the ROW_NUMBER means hash counters reset per tenant; legacy used a global counter.

Same dispute for `dim_section_hash` — legacy groups by `(Section_NID, Section_Instructors)` on the fact (`Schoology_py.ipynb:1300-1303`) but current sources from `dim_section` (`dim_section_hash.sql:33-35`). Numeric impact: zero (these don't feed KPI averages), but the join target for `fact_student_submissions_hash`'s teacher labels differs in edge cases.

### D-FACT-7 — Synthetic ID hash function for Subject_ID, Grade_ID, Assessment_ID

Legacy (`Schoology_py.ipynb:1203-1219`) uses `sha2(concat_ws("_", …), 256)` — SHA-256 of underscore-joined fields.
Current (`fact_student_submission.sql:271-275`) uses `uuid_2(school_id::text, grade)`, `uuid_2(school_id::text, assessment_type)`, `uuid_6(school_id::text, subject, assessment_type, grade, session, item_name)`.

The `uuid_N` helpers (`supabase/migrations/20260507000010_uuid_helpers.sql`) need inspection to confirm parity — they likely use a different hash function (UUID v5/MD5/SHA-1) than SHA-256. The values are opaque (M:1 joins), so what matters is that **all places** in the pipeline use the same function so dims and facts line up. If staging dims and the fact use matching helpers, downstream joins still work, but the values **will not match** the legacy fact dump byte-for-byte — irrelevant unless something downstream string-compares them. (This was out of scope for facts-only — flagging for the dims track.)

### D-FACT-8 — No `IsCorrect`/score derivation on the fact

PBIX has no `IsCorrect` column on `fact_student_submission` (confirmed: `05_dax_columns.dax` defines nothing on this table; `09_statistics.csv:188-222` shows the column doesn't exist on the published model). The correctness flag is computed inside the cubes — see `09_cubes/cube_question_summary.sql` and the user-summary cube (out of scope here).

Current fact also does not materialise an `IsCorrect` column. **No discrepancy at the fact layer**, but rounding/averaging behaviour of the equivalent of `IsCorrect` is what causes the anchor delta — pursue that in the cubes audit (track 6), not here. The likely root is `AVG(CASE WHEN points_received >= points_possible THEN 1 ELSE 0 END) * 100` evaluated at the question grain in current versus a `SUM(points_received)/SUM(points_possible)*100` at the row grain in legacy, or a tie-breaking rule on `points_received = NULL` rows.

### D-FACT-9 — Null-score row handling

Current keeps every submission row regardless of `points_received` value — including rows where `points_received IS NULL` (un-graded constructed-response items, for example). The dedupe `ORDER BY ... points_received DESC NULLS LAST` pushes NULL rows to the back, so a NULL-score row only survives if there is no non-NULL alternate.

Legacy keeps NULL-score rows too (no `WHERE points_received IS NOT NULL` anywhere in `build_fact_tables`). No discrepancy at the fact level on null-handling — divergence is downstream in cubes where `AVG(...)` either includes NULLs as 0 or excludes them. Investigate at the cube level.

## Derived Columns Matrix

PBIX has **zero** DAX calculated columns on `fact_student_submission` (confirmed via `05_dax_columns.dax` whole-file scan — only entries are on `dim_subject` and `cube_question_summary_overall`). The "DAX columns I'd expect on a per-question fact" (`IsCorrect`, `Score%`, `IsAttempted`, `IsMostRecentAttempt`, `WeightedScore`) **do not exist in PBIX** — they are computed inside cube SQL.

| Legacy field on `fact_student_submission` | Formula / source | Current equivalent | Where computed |
| --- | --- | --- | --- |
| `User_UID` | passthrough from `student_submissions` | `user_uid` | `fact_student_submission.sql:237` |
| `User_Name` | `concat(First_Name, ' ', Last_Name)` (notebook 1234) | `NULLIF(TRIM(CONCAT(COALESCE(first_name,''),' ',COALESCE(last_name,''))), '')` | `fact_student_submission.sql:241` |
| `User_Role_ID` | passthrough | `user_role_id` | `fact_student_submission.sql:243` — but always `'286170'` because of the filter (D-FACT-1) |
| `School_ID` | renamed from `User_School_ID` | `school_id` (UUID via staging) | `stg_student_submission.sql` |
| `Course_NID`, `Section_NID`, `Section_Code`, `Item_ID`, `Item_Name`, `First_Access`, `Latest_Attempt`, `Total_Time`, `Submission_Grade`, `Submission`, `Question_ID`, `Session`, `Assessment_type`, `Subject`, `Grade`, `Section`, `File_Name`, `Position_Number`, `Sub-Question`, `Answer_Submission`, `Correct_Answer`, `Points_Received`, `Points_Possible` | passthrough from staging | passthrough | `fact_student_submission.sql:244-267` |
| `User_id_ques_id` | `concat(User_UID,'-',Question_ID)` (notebook 1230) | `COALESCE(user_uid,'')||'-'||COALESCE(question_id,'')` | `fact_student_submission.sql:269` |
| `Qkey` | `concat(Session, Assessment_type, Subject, Grade, Question_ID)` (notebook 1232-1234) | **MISSING** — not selected into the fact. The header comment at `fact_student_submission.sql:16-20` notes "the column does not feed the notebook's `dim_question_data.qkey`". | not stored; downstream cubes recompute if needed |
| `Grade_ID` | `sha2(concat_ws('_', School_ID, Grade), 256)` (notebook 1245) | `uuid_2(school_id::text, grade)` — different hash function | `fact_student_submission.sql:271` |
| `Assessment_ID` | `sha2(concat_ws('_', School_ID, Assessment_type), 256)` (notebook 1246) | `uuid_2(school_id::text, assessment_type)` | `fact_student_submission.sql:272` |
| `Subject_ID` | `sha2(concat_ws('_', School_ID, Subject, Assessment_type, Grade, Session, Item_Name), 256)` (notebook 1247) | `uuid_6(school_id::text, subject, assessment_type, grade, session, item_name)` | `fact_student_submission.sql:273-275` |
| `Standard` | `Standard` from `ques_stand = questiondata[['Question_ID','Standard']].dropDuplicates()` (notebook 1252) | `qd.standard` from `dim_question_data DISTINCT (question_id, standard)` | `fact_student_submission.sql:138-141, 277` |
| `Identifier` | from `dim_standard` join on `Standard` (notebook 1257-1261) — fans out on multi-identifier collisions | LATERAL pin to lex-smallest `identifier` for exact match | `fact_student_submission.sql:168-176, 278` |
| `strand_ID` | from `dim_strand` join on `Identifier` (notebook 1263-1267) | `dst.strand_id` from `LEFT JOIN dim_strand ON dst.identifier = ds.identifier` | `fact_student_submission.sql:177-178, 276` |
| `User_id_ques_id_stand` (PK) | 8-part coalesce concat (notebook 1271-1289) | 9-part — adds `std` to legacy 8 (see D-FACT-4) | `fact_student_submission.sql:189-235` |
| `IsCorrect` | — not present on legacy fact — | — not present on current fact — | computed in cubes, not facts |
| `Score%` | — not present on legacy fact — | — not present on current fact — | computed in cubes |
| `IsAttempted` | — not present on legacy fact — | — not present on current fact — | n/a |
| `IsMostRecentAttempt` | — not present on legacy fact — | — not present on current fact — | implicit via dedupe |
| `WeightedScore` | — not present on legacy fact — | — not present on current fact — | computed in cubes |

PBIX expectation for fact row count: **none recorded** — `fact_student_submission` ships empty in the PBIX file (rows: 0). For Chapter 9 (27 students × 18 questions), a per-(student, question, attempt, answer) grain should land near 486 in the no-multi-attempt case. Current pipeline's stricter dedupe (D-FACT-2) and role filter (D-FACT-1) will produce ≤ 486; legacy can exceed 486 wherever multiple attempts or identifier-fanout occurred.

## Likely numeric impact

Most likely drivers of the anchor delta (66.9 → 65.4 on Grade Average), ranked by likelihood:

1. **D-FACT-3 (Identifier collapse)** — different identifier picked vs legacy for any standard with multi-identifier seed pollution. Doesn't change row count, but routes the row into a different `identifier`/`strand_id` bucket. Affects standard-summary KPIs primarily; may indirectly nudge question-level averages if cubes filter on identifier. *Magnitude: small for question-grade KPIs, large for standard-summary.*
2. **D-FACT-2 (Narrower dedupe partition)** — if any student had a multi-attempt row in the source, current drops it. The dropped attempt's `points_received` no longer contributes. *Magnitude: ~1pt per dropped row across a 27-student average — fits the observed delta.*
3. **D-FACT-1 (Role filter)** — if a non-student role row had `points_received` data, current excludes it. *Magnitude: likely 0-1 rows for this anchor; small.*
4. **D-FACT-4 (Extended PK adds rows)** — partially offsets D-FACT-2 by keeping more rows where multi-identifier alias exists. *Magnitude: small; depends on overlap with D-FACT-3.*
5. **D-FACT-5 (No TRUNCATE)** — only matters on re-runs with source changes; irrelevant for a first-run delta but a future correctness hazard.

The 28.9 → 27.8 "% incorrect" delta is the inverse of grade — consistent with the same root cause(s). The 96.1 → 96.3 max delta is small and points to a per-student maximum being computed off different deduped rows.

**Pursue first** in the cubes audit: how `cube_question_summary` and `cube_grade_summary` aggregate from the fact — specifically `AVG(...)` denominator (does it count NULL-score rows? does it count multiple rows per student?) and what column it derives `IsCorrect` from. The fact layer alone doesn't fully account for a 1.5pt move; the cube-level aggregation does.
