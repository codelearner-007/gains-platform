# 01 — Ingestion Audit

> Scope: how raw Schoology export artifacts are **discovered, downloaded, stored, and routed to a parser**. Numeric anchor case: `Chapter 9 Test, Grade 8, Schoology item_id 8359960427`. Legacy: 66.9% / 96.1% / 28.9%. New: 65.4% / 96.3% / 27.8%.

---

## What it does (current)

The current pipeline is a two-stage system. **Stage A is a Node + Playwright scraper** that lives outside this repo (`/Users/mac/Desktop/PS_P/gains legacy/scraper/schoology-exporter.js`, copied from the legacy tree because it is the only working source of CSVs today). It logs into `app.schoology.com`, discovers eligible assessments through the Schoology REST API, then drives the browser through the same "Export Stats → Submitted → Next → 4 checkboxes → Export → Transfer History → Download" UI dance the legacy bot used. It downloads **exactly three CSVs per assessment** (`Submission-Summary-*.csv`, `Question-Data-*.csv`, `Student-Submissions-*.csv`) and uploads each one to Azure Blob at `oea/pre_landing/Schoology/<session>/<categoryFolder>/<subject>/<grade>/<section>/`. After all assessments are uploaded, it writes a `<timestamp><SchoolName>Success.txt` marker file to the blob root listing `<blobPath>,<filename>` one line per CSV.

**Stage B is the Python ingestion orchestrator** in this repo: `backend/app/jobs/ingest_schoology.py`. For local dev it does NOT consume the Success.txt marker; it walks the local filesystem at `data/<SchoolShortName>/...` through `LocalBlobClient.list_files()` in `backend/app/jobs/blob_client.py:64-80`, yielding every `.csv` recursively. For each blob it (a) parses the **relative path** into a 6-tuple `(session, assessment_type, subject, grade, section, file_name)` via `backend/app/jobs/file_path_parser.py:61-90`, (b) SHA-256s the bytes, (c) skips if `(school_id, file_hash)` already exists in `ingested_files`, (d) dispatches to one of three parsers based on the file-name prefix, (e) batch-inserts into `raw_submission_summary`, `raw_student_submission`, or `raw_question_data`, and (f) records the file in `ingested_files`. Transformations (`run_transformations`) then build dims → facts → cubes against the raw rows in the same DB transaction.

The orchestrator is **idempotent by SHA-256 hash**: re-running with the same bytes is a no-op. Different bytes for the same logical assessment (re-export after a late submission) is treated as a *new* file and *both* old and new rows persist in `raw_*` — there is no "latest wins" logic at the ingestion layer. The dedupe instead happens downstream via `(school_id, source_file_hash, unique_key)` `ON CONFLICT DO NOTHING` on each raw INSERT and via merge keys in `transformations/`.

No Azure Blob client is implemented yet. `AzureBlobClient` (`backend/app/jobs/blob_client.py:101-115`) is a stub that raises `NotImplementedError`. So in any real-world scenario someone has to manually copy the scraper's outputs from blob (or from the scraper's `./downloads` dir) into the local `data/` tree before running ingestion. **No code in this repo touches Schoology's API**.

## How it does it (current)

| Step | File:line | Description |
|------|-----------|-------------|
| CLI entry | `backend/app/jobs/ingest_schoology.py:658-683` | argparse for `--school`, `--log-level`; calls `run_ingestion()` |
| Schools query | `backend/app/jobs/ingest_schoology.py:153-176` | `SELECT … FROM schools WHERE is_active = TRUE [AND short_name=:f OR schoology_building_id=:f OR name=:f]` |
| Blob client factory | `backend/app/jobs/blob_client.py:123-140` | env `INGESTION_SOURCE=local|azure`; defaults `local`, rooted at `<repo>/data` |
| List blobs | `backend/app/jobs/blob_client.py:64-80` | `Path(root).rglob("*.csv")`, yields `BlobInfo(path, last_modified, size_bytes)` |
| Download | `backend/app/jobs/blob_client.py:82-87` | `Path(root/blob_path).read_bytes()` |
| Path parse | `backend/app/jobs/file_path_parser.py:61-90` | Exactly 6 path parts, else `PathParseError`; strips `"<digit> - "` prefix off `assessment_type` |
| File-type routing | `backend/app/jobs/file_path_parser.py:111-128` | Filename startswith `Question-Data` → `question_data`; `Submission-Summary` → `submission_summary`; `Student-Submissions` → `student_submissions`; anything else → `PathParseError` |
| Idempotency | `backend/app/jobs/ingest_schoology.py:244-258` | `SELECT 1 FROM ingested_files WHERE school_id=:s AND file_hash=:h` |
| Per-school lock | `backend/app/jobs/ingest_schoology.py:563-573` | `pg_try_advisory_xact_lock` keyed off first 8 bytes of `school_id` UUID |
| Per-blob SAVEPOINT | `backend/app/jobs/ingest_schoology.py:584-602` | `session.begin_nested()` so one bad file doesn't abort the run |
| Submission-Summary parser | `backend/app/jobs/parsers/submission_summary.py:32-100` | Melts wide `Question 1..N` columns into long rows; `unique_key = schoology_id + question_label` |
| Student-Submissions parser | `backend/app/jobs/parsers/student_submission.py:31-119` | No melt; `unique_key = user_uid + item_id + question_id + position_number + answer_submission + points_received + points_possible + submission + correct_answer` |
| Question-Data parser | `backend/app/jobs/parsers/question_data.py:63-184` | Melts Standards columns; **does NOT melt Answer Breakdown** — treats duplicate "Answer Breakdown" header as `(count, pct)` pair; `unique_key` uses `answer_breakdown_count` (the integer count, not the column name) |
| INSERT statements | `backend/app/jobs/ingest_schoology.py:299-363` | `INSERT … ON CONFLICT (school_id, source_file_hash, unique_key) DO NOTHING` for all three raw tables |
| Record file | `backend/app/jobs/ingest_schoology.py:261-289` | `INSERT INTO ingested_files (school_id, blob_path, file_hash, file_type, rows_ingested, ingestion_run_id) … ON CONFLICT (school_id, file_hash) DO NOTHING` |
| School-root mapping | `backend/app/jobs/ingest_schoology.py:495-502` | School root = `schools.short_name` (e.g. Athenian → `data/Athenian/`) |

### What lives on disk for Chapter 9 Test

```
data/Athenian/2025-26/1 - Lesson  Assessments/Mathematics/Grade 8/Sec 1/
    Submission-Summary-Chapter-9-Test-2026-05-05-063438.csv   (28 lines = 27 students + header)
    Question-Data-Chapter-9-Test-2026-05-05-063438.csv        (149 lines)
    Student-Submissions-Chapter-9-Test-2026-05-05-063438.csv  (695 lines, 27 distinct User UIDs)
```

The 27 students in Submission-Summary include the lowest scorer (`Schoology_ID 36000605 / Charisma Williams`-likely, 26.3889%). Mean of the Gradebook Grade column across all 27 = **65.43**, which matches the new system's 65.4%. Dropping that single 26.39% student gives **mean=66.93, min=29.17, max=94.44**, which matches the legacy report exactly (66.9 / 96.1 / 28.9 — the 96.1 vs new's 96.3 is rounding off the same underlying 94.44 max, see Discrepancy #1).

> **Pivot observation:** the 1.5-point average gap, the 1.1-point min gap, and the near-zero max gap collectively look like *one student was in the legacy population that is not in the new population* (or vice-versa). The new file on disk has 27; legacy implied 26. Either the legacy *scraping run* captured 26 (e.g., before the 27th student submitted) or the legacy *processing* dropped that row. See Discrepancies below.

## What legacy did

### The legacy scraper (PAD bot, then Node replacement)

1. **Legacy v1 (PAD bot):** `/Users/mac/Desktop/PS_P/gains legacy/SchooloyAutomation/Athenasoft/Unmanaged/Workflows/ToDownloadResultsFromSchoology-D0D2403A-CA45-4ADF-ADD8-6A474545DC72.json.data.xml`. Browser-driven full traversal: My Courses → loop SubjectList × GradeList × SectionList → open course → Materials → All Materials → Tests/Quizzes → filter by `SchoolKeywordRegex=\b(Assessments)\b` and one of `LessonAssessments=(Chapter|lesson|Weekly|Module|Assessments)`, `UnitChapterAssessments=(unit)`, etc. → open assessment results → toggle → Export Stats → click **Submitted** filter → Next → tick 4 checkboxes (`export_submission_summary`, `export_questions[export_questions]`, `export_content[export_question_data]`, `export_content[export_submissions]`) → Export → Transfer History → loop `DownloadIndex=[1,2,3]` → download 3 CSVs → AzCopy to blob → write `C:\temp\<SchoolName>Success.txt`. The XML inputs show DownloadIndex of size 3 although 4 export checkboxes are ticked — Schoology apparently bundles `export_questions` into `Question-Data` rather than emitting a separate file. (Verified: real Athenian data on disk has **exactly 3 CSVs per assessment**, never 4.)
2. **Legacy v2 (Node Playwright):** `/Users/mac/Desktop/PS_P/gains legacy/scraper/schoology-exporter.js`. Replaces the PAD bot's discovery layer with the Schoology REST API (lines 105-289) while keeping the same browser export flow (lines 354-509). Reads `schools.json` (line 26) for per-school config (only Athenian, `buildingId=186370968`, `gradingCategoryRegex=(Chapter|lesson|Weekly|Module|Assessments)`, `coursePageLimit=200`, `dueDateWindowDays=14`, `downloadIndex=[1,2,3]`). Discovery filter: `type=assessment` AND grading-category title matches regex AND due date is within the last `dueDateWindowDays` days (default 14). Hardcoded carve-out at lines 250-254: if `school.name === "Athenian Academy of Technology and the Arts"`, force `categoryFolder = "1 - Lesson  Assessments"` (note: TWO spaces between "Lesson" and "Assessments"). Login uses `process.env.SCHOOLOGY_USERNAME/PASSWORD`. Uploads via `@azure/storage-blob` `BlockBlobClient.uploadData(...)`. Path scheme: `<academicYear>/<categoryFolder>/<subjectName>/<gradeName>/<sectionName>/` exactly matches the new system's expected on-disk layout under `data/<SchoolShortName>/`.

### The legacy ingestion (Synapse + Spark/Delta)

Spec: `data/_pbix_extract/40_schoology_py_spec.md` (rebuild spec for `Schoology_py.ipynb`), `data/_pbix_extract/41_pipeline_spec.md` (Synapse pipeline DAG). Actual notebook: `/Users/mac/Desktop/PS_P/gains legacy/OEA/modules/module_catalog/Schoology_Analytics/notebook/Schoology_py.ipynb`.

Pipeline DAG (per `41_pipeline_spec.md:14-46`):

```
BlobEventsTrigger (Success.txt)
   → 0_main_schoology
       → batch_completed_prelanding   (preland_batch_comp_files)
       → preprocess                   (preprocess_schoology_dataset)
       → ingestion                    (ingest_schoology_dataset)
       → dimension tables             (build_dimension_tables)
       → facts tables                 (build_fact_tables)
       → cube tables                  (cube_Build)
       → powerBI_datasets_update      (ExecutePipeline)
```

Critical legacy ingestion behaviors that have **no analog in the new code**:

1. **Schoology REST API user pulls.** Legacy `load_users` (`Schoology_py.ipynb:102-117`, `1_load_users_schoology` pipeline) calls `/users` **and `/users/inactive`**, unions them, lands as JSON. Legacy `load_roles` calls `/roles`. Legacy `3_Standards` pipeline runs `load_standard` against an external Standards API. These produce `dim_student`, `dim_teacher`, `dim_parent`, `dim_standard` etc. The new pipeline has none of this — there is no users JSON ingest, no `dim_student` from API, no standards JSON load. Filed under Discrepancy #2.
2. **Success.txt-triggered batch.** Legacy `preland_batch_comp_files` reads the Success.txt the scraper wrote and iterates `(folder, file)` lines, calling `preland_schoology_csv` per row. This **scopes the ingest to exactly the files the scraper said it just uploaded**, not the whole storage tree. New ingest does the opposite — it walks every CSV under `data/<school>/`. Filed under Discrepancy #3.
3. **Pre-processing per file** (`Schoology_py.ipynb:469-598`, `preland_schoology_csv`): reads ISO-8859-1 (new uses UTF-8-with-BOM, see Discrepancy #6), truncates `Question` and `Answer_Submission` to 7500 chars, melts wide columns, computes Unique_Key, writes pandas CSV to stage1 partitioned by `rundate=YYYY-MM-DD`.
4. **Question-Data melt + Standards filter** (`Schoology_py.ipynb:489-567`):
   - Melts ALL `Standards*` columns into a `(Standards, Standards_Val)` pair. Same in new (`backend/app/jobs/parsers/question_data.py:76-122`).
   - Then **drops rows where `Standards_Val` is null/empty IF the same Question_ID has any non-null Standards_Val elsewhere in the file** — i.e. groupby `Question_ID`, only keep null-Standards rows when the question has **no** standards at all. New parser does this row-by-row: it emits one row per non-null Standards value, falling back to `[None]` only when *that single row's* Standards columns are all empty. The two rules can diverge for files where some Standards columns have nulls for some questions. Filed under Discrepancy #5.
   - **Melts `Answer_Breakdown*` columns too** — turns the 2 duplicate "Answer Breakdown" columns (count + pct) into 2 long-format rows. New parser does **NOT** melt these; it treats them as a count/pct pair on one row (`backend/app/jobs/parsers/question_data.py:59-60`, `_AB_COUNT="Answer Breakdown"`, `_AB_PCT="Answer Breakdown__1"`). Filed under Discrepancy #4.
   - `Unique_Key = Item_ID + Question_ID + Correct_Answer + Position_Number + Answer_Option + Answer_Breakdown + Standards` where **`Answer_Breakdown` is the COLUMN NAME from the melt** (`Schoology_py.ipynb:556-563` uses `df_final['Answer_Breakdown']`, which is the var_name from `pd.melt(var_name='Answer_Breakdown', ...)`). New parser uses **`answer_breakdown_count`** (the integer count value) in the unique key (`backend/app/jobs/unique_key.py:46`). Filed under Discrepancy #4.
5. **Latest-rundate dedup** (`Schoology_py.ipynb:1185-1192`, also `40_schoology_py_spec.md:209-213`): after fact-build, partitions by every column except `(rundate, Unique_Key, Points_Received, Submission_Grade)` and keeps `row_number=1` ordered by `rundate desc`. This is how legacy handles **re-exports of the same assessment** (e.g., a student submits late, the scraper re-runs, a new file with more rows is uploaded — legacy keeps the latest version). New ingestion has no `rundate` concept and no latest-wins fact dedup. Filed under Discrepancy #7.
6. **Delete-stale-rows** (`Schoology_py.ipynb:729-768`, `40_schoology_py_spec.md:200-202`): on every re-run, Delta `MERGE … WHEN MATCHED DELETE` removes rows present in destination but not in the incoming source — restricted to a triplet like `(School_ID, Question_ID, Standards)`. This makes legacy a "full-replace within scope" model. New is "append-and-dedup-on-unique-key", with no removal of orphans.
7. **Per-CSV double-firing trigger** (`41_pipeline_spec.md:188-189, 196`): both the `Success.txt` blob trigger (which fires `0_main_schoology`) and the `.csv` blob trigger (which fires `4_prelanding_schoology`) match the same `pre_landing/` prefix. Per the spec, "in practice each CSV is prelanded twice on a real run". The Unique_Key + Delta MERGE saves this from double-counting at the data level, but it does mean legacy explicitly tolerates re-prelanding. New ingest tolerates re-runs only via the `(school_id, file_hash)` `ingested_files` short-circuit, which works only if the bytes are identical.

### Where the legacy ran from

- Trigger: `BlobEventsTrigger` on `oea/blobs/pre_landing/.../Success.txt` (`41_pipeline_spec.md:188`).
- Source path: `oea/pre_landing/Schoology/<tenant>/<academicYear>/<categoryFolder>/<subject>/<grade>/<section>/<filename>` (per scraper + per legacy bot doc).
- Spark CSV read options (`Schoology_py.ipynb:173`): `quote="\""`, `escape="\""`, `encoding=UTF-8`, `multiLine=true`, `header=true` for normal CSV reads, but the pre-landing read uses `encoding=ISO-8859-1` + `quoteAll=true` (`Schoology_py.ipynb:474` — spec §3 line 153). New uses `utf-8-sig` (`backend/app/jobs/parsers/common.py:60`).

## Discrepancies found

### 1. **Student-population mismatch is the most likely numeric driver**

- **Statement.** The data on disk has **27** Submission-Summary students for Chapter 9 Test, including one student at 26.3889%. New = mean across all 27 = 65.4. Legacy = mean across 26 (drop the 26.3889% student) = **66.93**. Min and max also line up: drop the 26.39 → next-lowest is 29.17 (legacy "28.9"); max remains 94.44 (legacy "96.1" is the same 94.44 with rounding noise from a different denominator or off-by-one rendering).
- **Evidence.**
  - 27 students confirmed: `wc -l Submission-Summary-Chapter-9-Test-2026-05-05-063438.csv = 28` (1 header + 27 rows); 27 distinct `User UID` in `Student-Submissions-Chapter-9-Test-2026-05-05-063438.csv`.
  - Mean of Gradebook Grade across all 27 = 65.43 → matches new system.
  - Mean of Gradebook Grade across 26 (drop 26.3889) = 66.93 → matches legacy.
- **Hypothesis for *why* legacy had one fewer student:**
  - **(a) Different scrape timestamp.** The legacy production scraper run happened before that 27th student submitted; the new run captured the late submission. The scraper itself enforces only `Submitted` filter on the export-stats screen (`schoology-exporter.js:386-388`, legacy XML "Span 'Submitted'") — meaning "students who have at least one submission". A student who submits *after* the legacy scrape but *before* the new scrape appears in only the new CSV.
  - **(b) Different population filter in legacy processing.** Legacy `dim_student` is sourced from `/users` + `/users/inactive` API pulls, then joined to facts. Any student missing from the dim table is silently dropped at fact-build (left join, then later filter on `dim_subject` etc. via inner joins in the cubes). New ingestion has no `dim_student` from API — it derives `dim_student` from `raw_student_submission` directly, so a student in the CSV but not in `/users` would appear in legacy as "unjoinable, dropped" but in new as a normal row.
  - **(c) "Active student" filter on `role_id == 286170`.** Legacy `dim_student` filter (`Schoology_py.ipynb:863`) restricts to students with `role_id == 286170`. The CSV column `User Role ID` is on every row (col 5 of Student-Submissions). New ingestion preserves it but does not currently filter on it — so if the 27th student is non-`286170` (e.g., a guest or teacher-account taking the test), legacy would drop them and new would not.
- **Numeric impact.** **HIGH.** This is the most plausible single-cause explanation that quantitatively reconciles 65.4→66.9 and 27.8→28.9. Whichever sub-hypothesis is right, the resolution is the same: confirm the student roster on the legacy side and align the new system's filter rule.

### 2. **The new pipeline never calls the Schoology API; legacy did three separate API loads** (users/inactive, roles, standards)

- **Statement.** Legacy enriches CSV facts with three external sources of metadata: `/users` + `/users/inactive`, `/roles`, and the Standards API. None of these are pulled by the new ingestion. The new system derives all student/teacher/standard info from the CSV columns alone.
- **Evidence.**
  - Legacy `load_users` / `load_users/inactive`: `Schoology_py.ipynb:102-117`; spec at `40_schoology_py_spec.md:138`.
  - Legacy `load_roles`: `Schoology_py.ipynb:114-117`.
  - Legacy `load_standard` (separate pipeline `3_Standards`): `41_pipeline_spec.md:126-131`.
  - New ingestion files (`backend/app/jobs/ingest_schoology.py`, `blob_client.py`, `file_path_parser.py`, `parsers/*.py`): zero HTTP calls, zero `requests`/`httpx` imports.
- **Hypothesis.** Without `/users/inactive` data, the new system cannot distinguish "student who exists but hasn't submitted" from "student who never existed". Without `dim_standard` from the Standards API, the new system relies on substring matching against `raw_question_data.standards_val` only.
- **Numeric impact.** **MEDIUM** for grade/min/max (would only matter if a particular student needs to be in `dim_student` but isn't — covered under Discrepancy #1 sub-hypothesis (b)/(c)). **HIGH** for per-standard performance (`Standards_Val` only joins to standard descriptions via the API-loaded `dim_standard` substring match, see `40_schoology_py_spec.md:336-356`). Since per-standard % rolls up the same students, the *per-student* numbers might agree even if standards-descriptions are missing.

### 3. **File discovery model is "walk the whole tree" vs "consume the Success.txt manifest"**

- **Statement.** Legacy ingestion is triggered by a `Success.txt` blob event and only reads the files listed in that manifest (`preland_batch_comp_files`). New ingestion is a CLI that walks the entire `data/<school>/` tree under `LocalBlobClient.list_files()`.
- **Evidence.**
  - Legacy: `41_pipeline_spec.md:188` (`BlobEventsTrigger` on `Success.txt`), `Schoology_py.ipynb:454-468` (`preland_batch_comp_files` opens the manifest, splits each line on `,`, calls `preland_schoology_csv` per row).
  - New: `backend/app/jobs/blob_client.py:64-80` (`LocalBlobClient.list_files()` recursively `rglob`s all `*.csv` under root) → `backend/app/jobs/ingest_schoology.py:576` (`bc.list_files(school_root)`).
- **Hypothesis.** In dev with a single dump of files on disk both produce the same result. **In production** they diverge: legacy ignores any orphan CSVs the scraper accidentally left behind (or files manually placed in storage). New would ingest them. Also, if anyone runs the legacy bot twice for the same assessment, the older CSV would still be in storage and would be picked up by the new walk — *but* the SHA-256 + `ingested_files` idempotency check skips it on a *re-run*. The first run would still ingest **all versions concurrently in the same pass**, which legacy would not.
- **Numeric impact.** **LOW** for the Chapter 9 Test anchor case (single CSV set on disk, no duplicates). **MEDIUM** in any environment where late re-exports happen — see also Discrepancy #7.

### 4. **Question-Data `Answer Breakdown` is melted in legacy but not in the new parser; the unique_key formula uses different inputs**

- **Statement.** Legacy melts both Answer_Breakdown columns into a long-format row (one row per question per option per count/pct), and the `Unique_Key` includes the **column-name string** (`"Answer_Breakdown"`/`"Answer_Breakdown.1"`). New parser keeps the duplicate "Answer Breakdown" headers as a `(count, pct)` *pair on one row* and uses the **integer count value** in the unique_key.
- **Evidence.**
  - Legacy: `Schoology_py.ipynb:539-552`: `df_final = df_melt1.melt(id_vars=..., value_vars=list_val_vars_AnsB, var_name='Answer_Breakdown', value_name='Answer_Breakdown_Val')`. Then `Schoology_py.ipynb:556-563`: `df_final['Unique_Key'] = … + df_final['Answer_Breakdown'].astype(str) + …` — that's the var_name from melt, i.e. literally `"Answer_Breakdown"` or `"Answer_Breakdown.1"`.
  - New: `backend/app/jobs/parsers/question_data.py:59-60, 95-122` — only count + pct are read; no melt. `backend/app/jobs/unique_key.py:27-49` — `question_data_unique_key(...)` takes `answer_breakdown_count: int` and stringifies the integer.
- **Hypothesis.** This roughly **halves the raw_question_data row count** compared to legacy (no 2× melt). It does NOT directly affect grade averages, but it does affect the cardinality of joins on `(item_id, question_id, position_number)` downstream. If any cube uses Answer_Breakdown row counts to weight averages, totals will differ.
- **Numeric impact.** **LOW** for Grade_Average / Highest / Lowest at the assessment level (those are computed off `raw_student_submission`, not Question-Data). **MEDIUM** for per-question answer-distribution percentages (Cube_QuestionIncorrectChoice_Summary in legacy, equivalent in new). **None** if the new parser's "1 row per question × option" is what the downstream code expects (verify against the dbt model).

### 5. **Question-Data Standards-melt empty-row rule is slightly different**

- **Statement.** Legacy keeps an empty `Standards_Val` row **only if the Question_ID has no non-null Standards anywhere in the file** (groupby Question_ID). New keeps an empty row only if **that single row** has all Standards columns empty (per-row decision).
- **Evidence.**
  - Legacy: `Schoology_py.ipynb:530`: `standards_group_counts = df_melt1.groupby('Question_ID')['Standards_Val'].transform(lambda x: x.notna().sum())` → drop empty-Standards rows when `standards_group_counts > 0`.
  - New: `backend/app/jobs/parsers/question_data.py:108-113`: `std_vals = [v for v in std_vals if v is not None]; if not std_vals: std_vals = [None]` → row-local decision, no groupby across the file.
- **Hypothesis.** For a Question-Data file with up to 4 Standards columns, a question that has Standards in row N1 but not N2 (same Question_ID, different Answer_Option) would: legacy → keep all Standards-bearing rows, drop the Nulls; new → keep the row but with `standards_val=None`. New would emit extra null-Standards rows that legacy would not. The opposite — a question with no Standards anywhere — has identical behavior (both keep one null-row).
- **Numeric impact.** **LOW.** The `unique_key` includes `standards_val` so extra null rows would generate distinct unique_keys and accumulate as extra rows in `raw_question_data`. This affects Cube_OverallPerformance_Summary if it counts standards per question, but does not change student grade averages.

### 6. **CSV encoding is different (UTF-8 vs ISO-8859-1)**

- **Statement.** Legacy reads CSVs as ISO-8859-1 (`Schoology_py.ipynb:474`). New reads as `utf-8-sig` (`backend/app/jobs/parsers/common.py:60`).
- **Evidence.**
  - Legacy spec note (`40_schoology_py_spec.md:153`): "For pre-landing CSVs the encoding is ISO-8859-1, plus quoteAll=true."
  - New: `backend/app/jobs/parsers/common.py:60`: `text = data.decode("utf-8-sig")`.
- **Hypothesis.** UTF-8 is the correct encoding for the scraper output (Playwright + Schoology returns UTF-8). ISO-8859-1 in legacy was a long-standing footgun — any non-Latin-1 character (en-dashes, smart quotes, emoji) would be **mojibake'd** in legacy but rendered correctly in new. For a math test that is mostly ASCII this changes almost nothing numerically, but the `Question` text body, `Answer Submission` body, and `Correct Answer` *strings* can differ. **Crucially, `unique_key` for student_submissions includes `answer_submission` and `correct_answer`** — if either contains a non-Latin-1 character that decodes differently, the unique_key will differ between the two systems and the row would not match on dedup.
- **Numeric impact.** **LOW** for the Chapter 9 Test anchor (mostly numeric answers). **MEDIUM** generally — would surface as orphan rows where dedup expected a match.

### 7. **No "latest version wins" or "rundate" semantics in new ingestion**

- **Statement.** Legacy uses `rundate=YYYY-MM-DD` partitioning at stage1 and a row_number-over-window dedup at fact-build (`Schoology_py.ipynb:1185-1192`) to keep only the latest version of each fact row across re-exports. New has no `rundate` column and no "latest wins" logic.
- **Evidence.**
  - Legacy: `Schoology_py.ipynb:1185-1192` (Window partition + row_number filter), spec `40_schoology_py_spec.md:209-213`.
  - New: `backend/app/jobs/ingest_schoology.py:299-363` — `ON CONFLICT (school_id, source_file_hash, unique_key) DO NOTHING`. The `source_file_hash` is in the conflict key, so two re-exports with different bytes produce two **distinct** rows in `raw_*` with no preference.
- **Hypothesis.** For an assessment that gets re-exported (e.g., teacher edits the answer key, more students submit late, etc.), the new system retains *both* versions in raw_* and the transformations layer is responsible for resolving them. If transformations don't apply a latest-wins rule, downstream aggregates will double-count.
- **Numeric impact.** **MEDIUM** *in production*. For the Chapter 9 Test anchor (single export on disk), **NONE**. But this is a latent foot-gun the audit should flag.

### 8. **No multi-school separation in legacy at the orchestration layer; new uses `schools.short_name` as a path prefix**

- **Statement.** Legacy pipeline has no `school_id` parameter; tenant routing happens purely from the path (`/oea/pre_landing/Schoology/<tenant>/...`). New uses `schools.short_name` as the root and treats each school separately.
- **Evidence.**
  - Legacy: `41_pipeline_spec.md:213` ("No `school_id` or `tenant` pipeline parameter anywhere. The pipeline is single-tenant from the orchestration layer's perspective. Per-school logic lives entirely inside the notebook.")
  - New: `backend/app/jobs/ingest_schoology.py:495-502` (`_school_root_for(school)` returns `school.short_name`); `153-176` (lookup schools from DB before walking).
- **Hypothesis.** Minor architectural difference. Won't affect numbers for a single-school anchor case. Could matter when multi-tenancy ships if `short_name` and the actual blob path tenant segment differ (e.g., `short_name="Athenian"` but blob writes to `Athenian Academy/...`).
- **Numeric impact.** **NONE** for current Athenian case. **LOW–MEDIUM** when additional schools are added.

### 9. **`assessment_type` parser strips the leading `"<digit> - "` prefix; legacy keeps the full directory name**

- **Statement.** New strips `"1 - "` off `"1 - Lesson  Assessments"` → `"Lesson  Assessments"` (`backend/app/jobs/file_path_parser.py:93-108`). Legacy keeps it (`Schoology_py.ipynb:218-227`, spec line 219: "Assessment_type is computed: if split[1] contains '-', take everything **after the first '-'**; else trim split[1]"). Wait — re-read: legacy also strips. Both do the same thing. **No discrepancy.** Logged here to confirm we considered it.
- **Numeric impact.** **NONE.**

### 10. **`ingested_files` idempotency uses `(school_id, file_hash)`; legacy used `rundate` + Delta MERGE — different re-run semantics**

- **Statement.** Re-running the new ingestion with the **same bytes** is a no-op. Re-running with **different bytes** produces a new row in `ingested_files` and appends new raw rows (no replacement of old). Legacy stage1 `oea.land(...)` partitioned by `rundate=YYYY-MM-DD` overwrites within the same `rundate`; stage2/3 use upsert by PK.
- **Evidence.**
  - New: `backend/app/jobs/ingest_schoology.py:244-289`.
  - Legacy: `41_pipeline_spec.md:248-250`.
- **Hypothesis.** As Discrepancy #7. Compounds: not just no latest-wins at facts, but also no overwrite at raw. Two different re-exports of the same assessment land as two independent rows in `raw_*` and accumulate forever.
- **Numeric impact.** Same as #7 — **MEDIUM** in production, **NONE** for the Chapter 9 anchor case.

## Likely numeric impact

| # | Discrepancy | Grade Avg | Highest | Lowest | Per-standard % | Notes |
|---|-------------|-----------|---------|--------|----------------|-------|
| 1 | Student-population mismatch (27 vs 26) | **HIGH** | LOW | **HIGH** | MEDIUM | Quantitatively reconciles new 65.4 vs legacy 66.9, new 27.8 vs legacy 28.9. The 96.3 vs 96.1 is rounding noise / same max student. |
| 2 | No `/users` + `/users/inactive` API pull in new | MEDIUM | LOW | MEDIUM | **HIGH** | Affects per-standard rollups (no `dim_standard` substring match) and the "active student" sub-hypothesis of #1. |
| 3 | Tree-walk vs Success.txt manifest | LOW | LOW | LOW | LOW | Only diverges in multi-batch or orphan-file scenarios. |
| 4 | Answer_Breakdown melt vs no-melt + unique_key uses count int not column name | LOW | LOW | LOW | LOW–MEDIUM | Doesn't change grade math; changes downstream join cardinality and incorrect-choice percentages. |
| 5 | Standards-empty-row rule (groupby vs row-local) | LOW | LOW | LOW | LOW | Minor row-count change in raw_question_data. |
| 6 | UTF-8 vs ISO-8859-1 | LOW | LOW | LOW | LOW | Anchor case is mostly ASCII. |
| 7 | No latest-wins / rundate | LOW (single-export case) | LOW | LOW | LOW | **MEDIUM in production** after re-exports. |
| 8 | Tenant routing model | NONE | NONE | NONE | NONE | Architectural. |
| 9 | `assessment_type` prefix-strip | NONE | NONE | NONE | NONE | Both systems strip; non-discrepancy. |
| 10 | `ingested_files` (hash) vs Delta MERGE | LOW | LOW | LOW | LOW | Same root cause as #7. |

**Bottom line.** The 65.4 → 66.9 / 27.8 → 28.9 / 96.3 → 96.1 gap is overwhelmingly explained by **Discrepancy #1**: the legacy report was computed over **26 students**, the new report is over **27 students**. The most likely sub-causes are (a) the legacy scrape ran before the 27th student submitted, or (b) the 27th student is missing from the legacy `dim_student` (built from `/users`+`/users/inactive`) and got dropped by an inner join in the cubes. Discrepancy #2 (missing API loads) directly feeds sub-cause (b) and is the gating fix in the ingestion layer if the cause turns out to be data-driven rather than scrape-timing-driven.

Everything else is structural and either (a) doesn't affect the assessment-level Grade Avg / Highest / Lowest math, or (b) only matters in production multi-batch / re-export scenarios that don't apply to a single Chapter 9 Test CSV on disk.
