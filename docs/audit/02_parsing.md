# 02 — Parsing Audit

**Scope:** Layer that turns a raw downloaded Schoology CSV into structured rows in memory before staging insert.
**Anchor case:** Chapter 9 Test, Grade 8, item_id `8359960427` (Athenian / Mathematics / Sec 1). Legacy 66.9 / 96.1 / 28.9 vs current 65.4 / 96.3 / 27.8 — gap is small (~1–1.5 pts) which usually indicates a different filter/dedupe/null-handling rule rather than a wholesale parse bug.

---

## What it does (current)

Three CSV parsers, all pure functions that take raw bytes and return Pydantic raw-row models:

1. **`backend/app/jobs/parsers/question_data.py`** — parses `Question-Data-*.csv`. Per CSV row × N Standards columns → emits one `RawQuestionDataRow` per non-empty Standards value (or one row with `standards_val=None` if none). Computes `question_no` by **dense rank over distinct `Question_ID` sorted lexicographically** (`question_data.py:166-169`), assigns `unique_key`, and performs in-file dedup on `unique_key`.

2. **`backend/app/jobs/parsers/student_submission.py`** — parses `Student-Submissions-*.csv` 1:1 (no melt). Each row → one `RawStudentSubmissionRow` with parsed types (timestamps, interval, decimals) and the `(user_uid, item_id, question_id, position_number, answer_submission, points_received, points_possible, submission, correct_answer)`-based unique key (`unique_key.py:61-88`).

3. **`backend/app/jobs/parsers/submission_summary.py`** — parses `Submission-Summary-*.csv`. Per student × Question-N column → one `RawSubmissionSummaryRow` melt-style.

Shared utilities live in **`backend/app/jobs/parsers/common.py`**: BOM-aware UTF-8 read, header-disambiguation (`disambiguate_headers`, `common.py:27-45`), per-row pad/truncate, numeric/decimal/string/timestamp/interval coercion, and 7500-char truncation for `Question` / `Answer Submission` (`common.py:154-160`).

Path-derived context (`session`, `assessment_type`, `subject`, `grade`, `section`, `file_name`) is injected by the ingestion caller via `ParsedPath` from `backend/app/jobs/file_path_parser.py:61-90`, not parsed out of the CSV body.

---

## How it does it (current)

### 1. CSV read shape
`common.py:48-96` — `csv.reader` over a single UTF-8 (BOM-stripped) string, header row taken first, duplicate column names disambiguated by appending `__1`, `__2`, etc. to second+ occurrences. Rows shorter than headers are padded with `""`; rows longer are truncated with a WARNING.

### 2. Question_no — dense rank on lexicographic Question_ID
```python
# question_data.py:166-169
qid_to_rank = {qid: idx + 1 for idx, qid in enumerate(sorted(qid_set))}
for r in out:
    if r.question_id is not None and r.question_id in qid_to_rank:
        r.question_no = str(qid_to_rank[r.question_id])
```
`qid_set` is a `set[str]` populated from `coerce_str(row.get("Question ID"))`. Sort is lex over strings. For Chapter 9 all 18 Question_IDs are 10-digit (`question_data.py` Chapter-9 sample confirms), so lex == numeric here.

### 3. "% correct" per student × question (Submission-Summary melt)
```python
# submission_summary.py:71-78
for q_label in question_cols:
    q_score_raw = row.get(q_label, "")
    q_score = coerce_decimal(q_score_raw)
```
**The cell value is taken AS-IS** as `question_score`. From the Chapter 9 sample header (`Question 1`..`Question 18`) and the first student row, values are `0` / `1` — i.e. binary 0/1 flag with no normalisation. Partial credit ≠ supported in this parser; a fractional value would be stored as the literal float.

### 4. Standards extraction
```python
# question_data.py:76, 108-111
standards_cols = [h for h in headers if h == "Standards" or h.startswith("Standards__")]
...
std_vals = [coerce_str(row.get(c)) for c in standards_cols]
std_vals = [v for v in std_vals if v is not None]
if not std_vals:
    std_vals = [None]
```
Each non-empty cell is preserved verbatim — no prefix normalisation, no canonicalisation. For Chapter 9 Question_ID `2269599900` the four cells observed are `MA.912.NSO.1.4`, `MA.9-12.MAFS.912.N-RN.1.2`, `MA.9-12.MAFS.912.N-Q.1.3`, `AI.MA.912.NSO.1.4` — each becomes its own `raw_question_data` row. The "long-form" preservation matches what PBIX expected on the `Standard` field.

### 5. Incorrect-choice details
**NOT computed in the parser layer.** Only the raw `(Answer Option, Answer Breakdown count, Answer Breakdown __1 pct, Correct Answer)` cells are captured into `RawQuestionDataRow` (`question_data.py:96-103`). Per-question incorrect-choice rollup with collected student-name lists is downstream of parsing — it must be reconstructed from `RawStudentSubmissionRow` rows in staging/transform SQL (track 3).

### 6. Multiple attempts / re-takes
**Parser captures EVERY row.** `Submission` is read as int (`student_submission.py:56`), `Submission #` as int (`submission_summary.py:67`), `Latest Attempt`/`First Access` as timestamps. The unique_key for `RawStudentSubmissionRow` includes `Submission` (`unique_key.py:69`), so multiple attempts → multiple raw rows with distinct keys. **No "latest only" selection happens in the parser** — that is supposed to happen in transformations (notebook line 1184-1192 latest-`rundate` window dedupe).

### 7. Missing-student handling
**Excluded.** The parser only reads rows physically present in the CSV. If a roster student never submitted, the export does not contain them and they will not appear in `raw_submission_summary` / `raw_student_submission`. No zero-fill is applied at parse time.

### 8. Question weighting
Preserved. `Points Possible`, `Points Received`, `Total Points`, `Most/Least/Average Points Earned` are all kept as decimals (`student_submission.py:54-55`, `question_data.py:91, 101-103`). The Submission-Summary "Question N" column is whatever Schoology wrote — 0/1 for binary, fractional for partial-credit — and is stored verbatim.

### 9. Standards-source alignment
The parser uses **only the Schoology-embedded `Standards*` columns** in `Question-Data-*.csv` (`question_data.py:76`). No separate alignment export is consulted at parse time. Alignment between long-form Schoology codes and canonical Florida codes happens later (out of scope for this audit; see standards seed files / `docs/standards-alignment.md`).

### 10. Path-derived context
`file_path_parser.py:61-90` — splits into `(session, assessment_type, subject, grade, section, file_name)` with `_strip_assessment_prefix` (`file_path_parser.py:93-108`) removing the `"1 - "` prefix and **preserving the double-space inside `"Lesson  Assessments"`** to match the legacy Athenian blob layout.

---

## What legacy did

There is **no equivalent CSV-parser layer in the legacy C# codebase**. The audit of `/Users/mac/Desktop/PS_P/gains legacy/EdvanceLearning/services/reporting/` confirms:

- `TenantConfigAppService.cs:368-557` (`GetSchoologyDataAsync`) walks the Schoology REST API to **discover assignments** and returns a list of `assignmentId:academicYear/category/subject/grade/section/` strings. That output is the *input* to a downstream scraper. **No CSV body is read in C#.**
- `SchoologySyncBackgroundJob.cs:34-56` is the Hangfire job wrapping that discovery call. It writes status JSON, nothing else.
- `services/lms/` and `services/GenAI/` contain no `*.cs` files matching `Parse|gradebook|StandardCode|QRA`.
- `/Users/mac/Desktop/PS_P/gains legacy/scraper/schoology-exporter.js` is the Node scraper that **downloads** the three CSVs per assignment (Question-Data / Submission-Summary / Student-Submissions). It performs no parsing.

The actual legacy parsing lived in the **PySpark notebook** `Schoology_py.ipynb` (re-documented in `data/_pbix_extract/40_schoology_py_spec.md`). The PBIX itself (`data/_pbix_extract/07_power_query.m`) only reads pre-built cubes from Azure Synapse, e.g.:

```m
// 07_power_query.m:3-7
let
    Source = Sql.Database("syn-oea-prodtest2-ondemand.sql.azuresynapse.net", "ldb_dev_s3_schoology_v0p1"),
    dbo_cube_question_summary = Source{[Schema="dbo",Item="cube_question_summary"]}[Data]
in
    dbo_cube_question_summary
```

So legacy parsing is the PySpark `preland_schoology_csv` function (spec §3, lines 469-598). Differences worth flagging:

### Legacy CSV read options (40_schoology_py_spec.md §3, line 153)
```python
df = spark.read \
    .option("encoding", "ISO-8859-1") \
    .option("quoteAll", True) \
    .option("multiLine", True) \
    .csv(..., header=True)
```
Encoding **ISO-8859-1**, not UTF-8. The current parser uses `utf-8-sig` (`common.py:60`). For pure ASCII content this is identical; for any byte ≥ 0x80 the parsers can diverge. The legacy spec notes the upstream API serves UTF-8, so the ISO-8859-1 read was likely defensive but lossy on real UTF-8 multibyte characters (e.g. en-dash inside the "Regular 9–12" remap on line 985).

### Legacy Question_No (spec §3, line 167)
```python
df_final = df_final.sort_values(by="Question_ID").reset_index(drop=True)
df_final['Question_No'] = rankdata(df_final['Question_ID'], method='dense')
```
`scipy.stats.rankdata` on a pandas `Series` of strings ranks **lexicographically** by string value when dtype is object. On numeric dtype it ranks numerically. The notebook calls it on a column read from CSV with no explicit cast, so it is `object` (string), matching the current parser. **No behavioural divergence here.**

### Legacy unique_key for Question-Data (spec §3, line 167)
```python
Unique_Key = Item_ID + Question_ID + Correct_Answer + Position_Number
           + Answer_Option + Answer_Breakdown + Standards
```
Current implementation (`unique_key.py:27-49`) concatenates the same fields in the same order — using `answer_breakdown_count` for `Answer_Breakdown` and `standards_val` (the melted singular) for `Standards`. **Matches.**

### Legacy Standards melt (spec §3, line 167)
> melts all `Standards*` columns into (`Standards`, `Standards_Val`); ... **Keeps a row per question even when value is empty — *unless* another row for the same `Question_ID` already has a non-null `Standards_Val`** (line 530).

Current behaviour (`question_data.py:108-111`) keeps non-null values; **if the row has NO non-null Standards cells, emits a single row with `standards_val=None`**. The legacy rule is global-per-Question_ID (suppress null row when ANY other row for that QID has a non-null value); the current rule is local-per-row. **DISCREPANCY** — see below.

### Legacy Answer_Breakdown melt
The spec line 167 says Question-Data also melts `Answer_Breakdown*` columns: `(Answer_Breakdown, Answer_Breakdown_Val)`. The current parser does NOT melt these; it pairs them by name: `Answer Breakdown` → `answer_breakdown_count`, `Answer Breakdown__1` → `answer_breakdown_pct` (`question_data.py:59-60, 97-98`). The CSV sample confirms there are exactly two columns named `Answer Breakdown`, holding (count, percentage). Current pairing **looks correct** for the observed CSV shape; the spec wording suggesting a melt may be outdated or only referred to old multi-column variants.

### Legacy submission_summary unique_key (spec line 168)
```
Unique_Key = Schoology_ID + Question
```
where `Question` is the column LABEL after melt. Current `submission_summary.py:75-78` uses `q_label` (e.g. `"Question 1"`). **Matches.**

### Legacy student-submission unique_key (spec line 169)
```
Unique_Key = User_UID + Item_ID + Question_ID + Position_Number + Answer_Submission
           + Points_Received + Points_Possible + Submission + Correct_Answer
```
Current `unique_key.py:61-88` — **identical order, identical concat semantics.**

### Legacy Question / Answer_Submission truncation (spec line 153)
`SUBSTRING(Question, 1, 7500)` — current implements via `truncate_question` (`common.py:154-160`) at exactly the same 7500-char boundary applied to `Question` and `Answer Submission`. **Matches.**

### Legacy multi-attempt handling
Parser keeps everything; latest-rundate dedupe runs in `build_fact_tables` (spec §3 line 204-211):
```python
key_columns = [c for c in df_Student_Submissions.columns
               if c not in ("rundate","Unique_Key","Points_Received","Submission_Grade")]
w = Window.partitionBy(key_columns).orderBy(F.col("rundate").desc())
df = df.withColumn("rn", F.row_number().over(w)).filter("rn=1").drop("rn")
```
Current parser also keeps everything — but **whether the equivalent dedupe ever runs in the current Postgres pipeline must be confirmed in track 3** (staging SQL). If it does not, the same (User_UID, Item_ID, Question_ID, Position_Number) appearing in multiple `Submission` rows will be double-counted in averages.

### Legacy "Submission" handling
Spec lines 1180-1192 and the fact build: rows with multiple `Submission` values for the same student/question are deduplicated to "latest rundate". The fact then sums `Points_Received` and `Points_Possible` per student × item. **There is no "highest score" or "first attempt" rule** — it is "latest export row wins".

### Legacy missing-student handling
Same as current: the export is the universe. No zero-fill at parse time. Cubes compute means over students present. (Verified via `Cube_Grade_Summary` spec §7 line 1337 — it averages over what is in the fact.)

### Legacy Standard ↔ Standards substring join (spec §8)
> `df_dim_question_data.Standard.contains(dim_standard.Standards)` — meaning the long-form `Standard` from raw_question_data **string-contains** the short canonical `Standards` code.

This is a TRANSFORMATION-LAYER (track 3) concern but it depends on the parser preserving the long form. Current parser does preserve the long form (verbatim). **Matches.**

---

## Discrepancies found

| # | Area | Legacy behaviour | Current behaviour | Likely effect |
|---|------|------------------|-------------------|---------------|
| 1 | **CSV encoding** | `ISO-8859-1` (`spec §3 line 153`) | `utf-8-sig` (`common.py:60`) | None for ASCII; minor character corruption (e.g. en-dash) where present in real UTF-8 multibyte input. Likely NOT cause of Chapter 9 deltas. |
| 2 | **Question-Data Standards melt "global-null suppression"** | Spec §3 line 167: "Keeps a row per question even when value is empty — *unless* another row for the same `Question_ID` already has a non-null `Standards_Val`" | Current applies the rule per-row only (`question_data.py:108-111`). A Question_ID with one non-null Standards row + one all-null Standards row would: legacy keep ONLY the non-null; current keep both. | Track 3 dedupe may collapse this. If not, an extra `(question_id, NULL standard)` row can leak into `dim_question_data` and double-count in standard-aware aggregations. |
| 3 | **Question_No tie-handling** | scipy `rankdata(..., method='dense')` over the FULL row set (with duplicates from melt) — produces equal ranks for tied Question_IDs (`spec §3 line 167, notebook line 567`) | Current builds rank from the **distinct set** of Question_IDs (`question_data.py:80, 166`) and assigns to every row. Behaviourally identical because dense rank is dedup-stable, **but** legacy operates on the sorted/melted full frame which can re-order in pandas; mismatched if the column ever contains numeric-typed values. | Low risk for the Chapter 9 case (all QIDs are equal-length numeric strings). |
| 4 | **Multi-attempt dedupe at parse time** | None (kept in parser, deduped in fact build) | None (kept in parser, deduped in transform — IF a "latest" rule exists in track 3) | Track 3 dependency. If track 3 has no latest-only window, current pipeline can sum (Points_Possible / Points_Received) across attempts → drift on averages. |
| 5 | **"Question N" cell semantics** | Treated as a 0/1 indicator AND used to drive `% correct`. Notebook line 1605-1606: `Choice_Submission_Count = sum(case when Points_Received < Points_Possible then 1 else 0 end)` derives correctness from **Points_Received / Points_Possible in Student-Submissions**, not from the Submission-Summary "Question N" column. | Current parser preserves Submission-Summary "Question N" as `question_score` (decimal). Whether the downstream computation uses Student-Submissions `Points_Received / Points_Possible` or `Submission_Summary.question_score` is an SQL-layer choice. | If a transform uses `question_score` from `raw_submission_summary` directly, and that value is 0/1-rounded by Schoology, it loses partial-credit information that `Points_Received / Points_Possible` would retain. This is a **plausible 1-1.5 point drift cause**. |
| 6 | **Incorrect-choice details** | Built in cube layer from `Student-Submissions` (`Cube_Question_Summary`, spec §7 lines 1593-1689). Parser only captures Answer_Breakdown count+pct columns. | Same: parser only captures Answer_Breakdown columns. | None at parse layer. Both pipelines defer this to the cube/transform layer. Confirm parity downstream. |
| 7 | **No "User role name" column captured** | Notebook stores all columns; `User_role_name` is present in Student-Submissions CSVs | `student_submission.py` reads `User Role ID` but not `User role name` (`student_submission.py:82`). The CSV header includes both: `"User Role ID","User role name"`. | Cosmetic. role_id is sufficient for filtering. |
| 8 | **`coerce_str` returns the raw string (no strip)** | Notebook does not strip individual cells either | `common.py:145-151` — empty → None, else as-is. So `" MA.912.NSO.1.4"` with a leading space would be a distinct standards value from `"MA.912.NSO.1.4"`. | Low risk in observed data (no leading whitespace in Chapter 9 sample), but a single export with stray whitespace would shard the standard. |
| 9 | **`coerce_int` float fallback** | Pandas auto-converts `"5.0"` to `5` silently | Current does the same (`common.py:115-122`) but logs WARNING | Identical numerics. |
| 10 | **Path-derived assessment_type** | Spec §3 line 219: take everything **after the first `-`** then trim | Current matches (`file_path_parser.py:104-108`); preserves "Lesson  Assessments" double space | Match. |
| 11 | **Within-file dedup by unique_key** | Spec line 167-169 — no in-parser dedup explicit, but the downstream Delta MERGE collapses duplicates | Current does in-parser dedup (`question_data.py:176-184`) before insert | Match in outcome. |

---

## Likely numeric impact

For the anchor case (Chapter 9 Test, item_id `8359960427`, Grade 8, Sec 1, ~27 students, 18 questions):

- **Discrepancy #2** (Standards null-row suppression): If any Question_ID in Chapter 9 has some rows with non-null Standards and some all-null, current keeps the extra null row. Without track-3 dedupe this would inflate the count of `dim_question_data` rows for that question but **should not** directly shift the Grade Avg of 66.9 vs 65.4 — Grade Avg is `sum(Points_Received) / sum(Points_Possible)` over students. **Low impact on the 1.5-pt delta.**

- **Discrepancy #4** (multi-attempt dedupe): If Submission-Summary or Student-Submissions contains second attempts (a few students with `Submission # = 2`), legacy keeps only the latest; current parser keeps everything. A few re-takes that pulled down individual averages could explain the 1.5-pt direction (current lower than legacy). **Plausible primary cause; verify in track 3 staging.**

- **Discrepancy #5** ("Question N" cell vs Points_Received/Points_Possible): If track 3 uses `raw_submission_summary.question_score` (Schoology's 0/1 rounding) for the Grade Avg numerator, and legacy uses `raw_student_submission.points_received / points_possible`, results diverge whenever Schoology partial-credit was rounded. The Chapter 9 sample shows `Submission Score` of 8/18 = 44.4% — but the CSV header shows binary 0/1 values. **Plausible secondary cause if track 3 uses the wrong source column.**

- **Discrepancy #1** (encoding): None for this anchor — file is pure ASCII.

- **Highest / Lowest deltas** (96.1→96.3, 28.9→27.8): These move ~0.2 and ~1.1 points in OPPOSITE directions, consistent with one student's score moving (a re-take or a single-question re-grade) rather than a systematic parser bug. **Strongly suggests a single-row dedupe issue (Discrepancy #4) rather than a parsing-level error.**

**Conclusion:** The parser layer alone is unlikely to be the primary source of the 66.9 → 65.4 drift. The parsers are direct, faithful ports of `preland_schoology_csv` (spec §3 lines 469-598) and preserve all the legacy unique-key formulas and truncation rules. The probable source is downstream:
- Track 3 (staging / transform SQL) — whether it runs the latest-rundate dedupe (Discrepancy #4) and which column it sources for "% correct" (Discrepancy #5).
- The "global Standards null suppression" rule (Discrepancy #2) is a known parser delta but its numeric effect is filtered by track 3 dedupe; worth eliminating only after track 3 is confirmed.

**Recommended cross-track verification:**
1. Run a row count on `raw_student_submission WHERE item_id='8359960427'` and check if `(user_uid, question_id, position_number)` is unique. If not, the parser is correctly preserving multiple attempts and the transform must dedupe — see track 3.
2. Confirm in track 3 whether the per-student Grade is computed from `raw_student_submission` (legacy-equivalent) or from `raw_submission_summary.question_score` (which loses partial credit if Schoology rounds).
3. Spot-check the Standards melt: count `raw_question_data` rows with `standards_val IS NULL` per `(item_id, question_id)`. Compare against the count of non-null rows for the same key; if both exist, the legacy "global null suppression" rule would have dropped the null row.
