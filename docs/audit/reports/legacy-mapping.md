# Legacy → Current Platform Mapping for the Six Paginated Reports

> Research-only reverse-engineering pass. No code changes here. Every claim
> is cited as `path:line` against either the legacy repo
> (`/Users/mac/Desktop/PS_P/gains legacy/`) or the PBIX extract artifacts
> (`/Users/mac/Desktop/PS_P/gains-platform/data/_pbix_extract/`).
>
> Scope: the 6 PBIX pages used for paginated/PDF rendering:
> - **ord 6**  — Question Summary Report
> - **ord 7**  — Question Summary Report - teacher subtotal
> - **ord 16** — Question Summary Report - header highlights
> - **ord 11** — Question Response Analysis
> - **ord 12** — Question Response Analysis by Teacher
> - **ord 13** — Question Response Analysis by Standard and Teacher
>
> Cross-references the current platform's transformations in
> `backend/app/transformations/09_cubes/*.sql` and repository methods in
> `backend/app/repositories/cube_repository.py`.

---

## §0. TL;DR — How a paginated report is produced in legacy

```
                ┌──────────────────────────────────────────────┐
                │ 1. Schoology Question-Data CSV exports       │
                │    (one per assessment) land in ADLS         │
                └──────────────────────────────────────────────┘
                                  │  (Synapse pipelines 1..8)
                                  ▼
                ┌──────────────────────────────────────────────┐
                │ 2. Spark notebook                            │
                │    Schoology_Analytics/notebook/             │
                │    Schoology_py.ipynb                        │
                │      method `Schoology.cube_Build` (single   │
                │      cell, lines 1322–2473) emits ALL cubes  │
                │      to stage3/Published/schoology/v{ver}/   │
                │      Cube_*  as parquet                      │
                └──────────────────────────────────────────────┘
                                  │  (orchestrated by
                                  │   `9_cube_tables_schoology.json`
                                  │   Synapse pipeline)
                                  ▼
                ┌──────────────────────────────────────────────┐
                │ 3. Synapse Serverless SQL                    │
                │    db = `ldb_dev_s3_schoology_v0p1`          │
                │    schema=dbo                                │
                │    cube_*, dim_*, fact_* are EXTERNAL TABLES │
                │    over the parquet (`oea.add_to_lake_db`)   │
                └──────────────────────────────────────────────┘
                                  │
                                  ▼
                ┌──────────────────────────────────────────────┐
                │ 4. Power BI Service                          │
                │    PBIX `Sql.Database("syn-oea-prodtest2-    │
                │    ondemand.sql.azuresynapse.net", "ldb_dev_ │
                │    s3_schoology_v0p1")`                      │
                │    Each table is one Power Query `let`-      │
                │    expression in 07_power_query.m            │
                └──────────────────────────────────────────────┘
                                  │
                                  ▼
              Paginated reports (RDL-style `rdlVisual`) print
              one PDF page per Item_ID by binding the M query
              to a `SchoolID` / `FilterExpression` parameter.
```

**Key takeaways:**
- There is no .NET / EdvanceLearning code path for the paginated reports. The
  EdvanceLearning C# tree (`EdvanceLearning/`) hosts the LMS, GenAI, gateway,
  identity, lms, lti, administration services — none of them produce cube
  tables. The cube layer is exclusively the Spark notebook
  (`gains legacy/OEA/modules/module_catalog/Schoology_Analytics/notebook/Schoology_py.ipynb`).
- All six reports share **exactly the same upstream Spark pipeline** —
  `cube_Build` runs once per refresh and emits 6 published parquet folders:
  `Cube_Grade_Summary`, `Cube_School_Summary`, `Cube_Standard_Summary`,
  `Cube_Question_Summary`, `Cube_QuestionIncorrectChoice_Summary`,
  `Cube_Question_Summary_Overall`, `Cube_OverallPerformance_Summary`,
  `Cube_User_Summary` (paginated variant).
- All 6 reports differ from one another only in:
  - the `rdlVisual`'s layout-XML (live inside the PBIX/RDL bytes — NOT in
    legacy SQL),
  - the M query's filter (`Item_ID` page filter, `SchoolID` parameter,
    `FilterExpression` text substring), and
  - the page-level Titles / KPI strips (DAX measures pulling from
    `cube_question_summary_overall`).

Hence: **all 6 paginated reports are recreatable on the current platform by
exposing only the existing cubes** (`cube_question_summary_overall`,
`cube_school_summary`, `cube_grade_summary`, `cube_standard_summary`,
`cube_questionincorrectchoice_summary`, `cube_user_summary`,
`cube_overallperformance_summary`) plus a small number of dimension fields
that several reports already consume.

---

## §1. Field → Source matrix (all 6 reports combined)

The matrix is collapsed across the 6 reports because their visual lists are
nearly identical (see `20_pages.md` lines 128–344). Differences between
reports are called out in the per-report sections below.

Convention for the "current platform" column:
- `cube_X.col`          → already produced.
- `cube_X.col*`         → produced but under a different name; see note.
- `MISSING — <note>`    → not in current platform; would need to be added.
- `derive-at-query`     → not a column, computed by frontend / repository.

### §1.1 Header / chrome (rows in every report)

| Report visual / field                                  | Legacy source (table.column)                                                                            | M expression (file:line)              | Current-platform equivalent                                          |
|--------------------------------------------------------|---------------------------------------------------------------------------------------------------------|---------------------------------------|----------------------------------------------------------------------|
| `Titles.H1 - Longitudinal`                             | DAX measure on `Titles` (literal `"Paginated PDF Report \|"`)                                           | `04_dax_measures.dax:656`             | derive-at-query (static string in component)                         |
| `Titles.H2 Course and Unit`                            | DAX measure CONCATENATEX(`dim_subject.Grade`, `dim_item.Item_Name`)                                     | `04_dax_measures.dax:340`             | derive-at-query: `dim_item.item_name` + `dim_subject.grade`          |
| `Titles.H2 - Assessment Type`                          | DAX measure CONCATENATEX(`dim_subject.Assessment_type`)                                                 | `04_dax_measures.dax:320`             | `dim_subject.assessment_type`                                        |
| `Titles.H1 - Report Header`                            | DAX literal `"Grade Performance by Strand"`                                                             | `04_dax_measures.dax:612`             | static                                                               |
| `Titles.__Title`                                       | DAX literal `"Assessments Dashboard"`                                                                   | `04_dax_measures.dax:364`             | static                                                               |
| `Titles.Instructor(s):`                                | DAX `CONCATENATEX(DISTINCT(dim_Item[Section_Instructors]), …)`                                          | `04_dax_measures.dax:279`             | `dim_item.section_instructors` (already on `dim_item`)              |
| `SchoolLogo_Parameter.SchoolLogo_Parameter`            | M parameter literal — references PBIX parameter `SchoolLogo`                                            | `07_power_query.m:196`                | MISSING — backend should emit `assessment.school_logo_url`           |
| `SchoolName_Parameter.SchoolName_Parameter`            | M parameter literal — references PBIX parameter `School_Name`                                           | `07_power_query.m:187`                | MISSING — backend should emit `assessment.school_name`               |

### §1.2 KPI strip (multiRowCard on every report)

This is the same 5-field strip on all six reports
(`20_pages.md` lines 145–146 / 172–173 / 198–199 / 226–227 / 254–255 / 281–282 / 308–309 / 335–336 / 362–363).

| PBIX field                                              | Legacy DAX measure / source                                                                          | DAX file:line                  | Current-platform equivalent                                                                |
|---------------------------------------------------------|------------------------------------------------------------------------------------------------------|--------------------------------|--------------------------------------------------------------------------------------------|
| `Key Measures.Total Questions`                          | `MEASURE [Total Question] = DISTINCTCOUNT('cube_question_summary_overall'[Question_No])`             | `04_dax_measures.dax:148`      | `cube_school_summary.total_questions` (already SQL `countDistinct(question_id)`); also `cube_question_summary_overall.question_no` distinct |
| `Key Measures.Total Students`                           | `MEASURE [Total Student] = SUMX(SUMMARIZE(cube_school_summary, [Item_ID], MAX([Total_Students])))`   | `04_dax_measures.dax:134`      | `cube_school_summary.total_students`                                                       |
| `Key Measures.Score`                                    | `MEASURE [Score] = SUM('cube_questionincorrectchoice_summary'[Total_Score])`                         | `04_dax_measures.dax:482`      | `cube_questionincorrectchoice_summary.total_score` (sum); equivalent: `cube_school_summary.total_score` |
| `Sum(Student Submissions.Points Possible)`              | "Student Submissions" is a virtual / display-group alias of `fact_student_submission`; sums `Points_Possible` | n/a (PBIX-side rename)         | `cube_school_summary.total_possible_point`                                                 |
| `Key Measures.% of Correct Answers`                     | Effectively `MEASURE [Grade Average] = AVERAGE('cube_question_summary_overall'[Grade_Average])`      | `04_dax_measures.dax:168`      | `cube_school_summary.grade_average`                                                        |

Notes:
- `Key Measures` and `Student Submissions` are **display-group renames** in
  the PBIX semantic model — they do not correspond to physical tables. The
  schema dump (`03_schema.csv`) only lists `Titles`, `Drill Through Report`,
  `SchoolLogo_Parameter`, `SchoolName_Parameter` as non-physical, and shows
  no rows for `Key Measures` or `Student Submissions` (verified: zero hits
  on `^Key Measures,` / `^Student Submissions,` in `03_schema.csv`).
- All five strip values can be served by one repository call against
  `cube_school_summary` for the selected `item_id`.

### §1.3 The big `rdlVisual` table — Question Summary family (ord 6, 7, 16)

`20_pages.md:147-149` (ord 6) / `:174-176` (ord 7) / `:365-367` (ord 16) all
show the **same RDL field list**:

```
tables: dim_item, dim_subject
fields: dim_item.Item_ID, dim_item.Item_Name,
        dim_subject.Assessment_type, dim_subject.Grade,
        dim_subject.Session, dim_subject.Subject
```

This is misleading: the RDL container only **declares** dim_item + dim_subject
as the page-filter dataset. The actual row-level data inside the RDL comes
from `cube_question_summary_overall` (verified by the M expression in
`07_power_query.m:161-174`, and by the DAX measures called inside the RDL
RDLX bytes — see `__FirstFormatted_correct_`, `__FirstFormatted_Incorrect_*`
in `04_dax_measures.dax:726, 778, 897`).

| RDL column           | Legacy source (cube.column)                                                                                 | Legacy producer (file:line)             | Current-platform equivalent                                                |
|----------------------|-------------------------------------------------------------------------------------------------------------|-----------------------------------------|----------------------------------------------------------------------------|
| `No.` (question #)   | `cube_question_summary_overall.Question_No` + DAX `Sorting Question_No` (calc col `INT([Question_No])`)     | `Schoology_py.ipynb:264` (Question_No groupBy); `05_dax_columns.dax:20-21` (sort key) | `cube_question_summary_overall.question_no` + new `sorting_question_no` (already in current SQL `09_cubes/cube_question_summary_overall.sql:280`) |
| `Question`           | `cube_question_summary_overall.Question` via DAX `questionDax = FIRSTNONBLANK(…[Question],1)`               | `04_dax_measures.dax:719`               | `cube_question_summary_overall.question`                                   |
| `% Correct`          | `Sum(cube_question_summary_overall.Grade_Average)` (cell-color via `Performance Color Question`)            | `04_dax_measures.dax:576`               | `cube_question_summary_overall.grade_average` (current SQL already emits)  |
| `Correct Answer`     | DAX `__FirstFormatted_correct_` — line-break-joined `Position_Number: Correct_Answer` (DAX 726-772)         | `04_dax_measures.dax:726-772`           | `cube_question_summary_overall.correct_answer` + `position_number`; concat to do at the API layer |
| `Incorrect Choice Details` | DAX `__FirstFormatted_Incorrect_Choice_Details` — assembled from `Incorrect_Choice_Details` and `Position_Number`, blank when Grade_Average=1 | `04_dax_measures.dax:778-892`           | `cube_question_summary_overall.incorrect_choice_details` (already produced); blanking logic at API |
| `Incorrect Details Name` | DAX `__FirstFormatted_Incorrect_Details_Name` (same shape with names instead of %)                      | `04_dax_measures.dax:897-…`             | `cube_question_summary_overall.incorrect_details_name`                     |
| `Standards`          | DAX `CombineStandardsColumn = CONCATENATEX(DISTINCT([Standards]), …)`                                       | `04_dax_measures.dax:683-690`           | `cube_question_summary_overall.standards`                                  |
| `Description`        | DAX `CombineDescriptionsColumn` — picks `MAX(Description)` for the lexically-first non-"Other" Standards    | `04_dax_measures.dax:1200-1254`         | `cube_question_summary_overall.description` (current SQL emits via join to `dim_standard`, file `09_cubes/cube_question_summary_overall.sql:294`) |

### §1.4 The big `rdlVisual` table — Question Response Analysis family (ord 11, 12, 13)

ord 11 (`20_pages.md:283-285`) reads explicitly from
`cube_question_summary_overall`, `SchoolLogo_Parameter`, `Titles`,
`dim_item`, `dim_subject`.

ord 12 and ord 13 declare only `dim_item, dim_subject` at the visual level
(`:310-312` and `:337-339`), but follow the identical RDL layout — the QRA
RDL's dataset binds via M parameter just like the Question Summary RDLs.

QRA tables additionally pull these DAX measures (mostly the same set):

| RDL column                                          | Legacy source                                                            | DAX file:line               | Current-platform equivalent                  |
|-----------------------------------------------------|--------------------------------------------------------------------------|-----------------------------|----------------------------------------------|
| `Subject_ID` (page-filter)                          | `cube_question_summary_overall.Subject_ID`                               | (column, not measure)       | `cube_question_summary_overall.subject_id`   |
| `Titles.H3 - Teachers` (group header)               | (not in 04_dax_measures.dax — listed only in 22_fields_per_page.json)    | n/a                         | derive-at-query: `dim_item.section_instructors` group label |

For ord 13 ("by Standard and Teacher") the RDL adds an extra **row-grouping
level** over `Standards`. The data binding is otherwise identical.

### §1.5 Other helper tables

| Helper table              | Where it lives                                                          | How it's populated in legacy                                                                                          | Used by reports                                       |
|---------------------------|-------------------------------------------------------------------------|-----------------------------------------------------------------------------------------------------------------------|-------------------------------------------------------|
| `Titles`                  | PBIX-internal (no rows, only measures)                                  | M expression literally `let Source = "" in Source` — `07_power_query.m:130-135`. Measures attach to this empty table.   | All 6 reports                                          |
| `Drill Through Report`    | PBIX-internal — base64-gzipped inline JSON                              | `07_power_query.m:177-184` (`Table.FromRows(Json.Document(Binary.Decompress(Binary.FromText("rZRda8…", …))))`)         | Home page slicer only (not the 6 paginated reports)   |
| `Report Short Name`       | Same shape as above                                                     | `07_power_query.m:96-102`                                                                                              | Home page slicer only                                  |
| `SchoolLogo_Parameter`    | PBIX parameter (single-string)                                          | `07_power_query.m:196-202` (literal `Source = SchoolLogo`)                                                            | All 6 reports                                          |
| `SchoolName_Parameter`    | PBIX parameter (single-string)                                          | `07_power_query.m:187-193`                                                                                            | (Incorrect Answer Details page; not paginated 6 but rendered server-side similarly) |

These six helper tables exist ONLY inside the PBIX file; legacy
materializes none of them in SQL. The current platform should emit them
through the report payload (e.g. `assessment.school_name`,
`assessment.school_logo_url`) — see §3.4 below.

---

## §2. Per-report sections

### §2.1 Question Summary Report (ord 6)

**Visuals** (verified `20_pages.md:128-153`): 4 multiRowCards (header
titles), 1 textbox, 1 `rdlVisual`, 1 schoolLogo image, 1 actionButton.

**Tables read** (PBIX field list — see `22_fields_per_page.json` block for ord 6):
- `Titles`                    (header text only)
- `Key Measures`              (display-group alias; resolves to
                              `cube_question_summary_overall` + `cube_school_summary` measures)
- `Student Submissions`       (display-group alias; resolves to
                              `fact_student_submission.Points_Possible`)
- `dim_item`                  (Item_ID page filter, Item_Name)
- `dim_subject`               (Grade, Subject, Session, Assessment_type)
- `cube_question_summary_overall` (inside RDL — see §1.3)
- `SchoolLogo_Parameter`

**Legacy producers:**
- `cube_question_summary_overall` ← `Schoology_py.ipynb:1953-2189`
  inside `cube_Build` (the `Cube_Question_Summary_Overall` block).
- `cube_school_summary`           ← `Schoology_py.ipynb:1346-1370`
  (the `Cube_School_Summary` rollup block).
- `dim_item`                      ← `Schoology_py.ipynb:931-943`.
- `dim_subject`                   ← `Schoology_py.ipynb:1175-1178`.
- `fact_student_submission`       ← `Schoology_py.ipynb:1222-1294`.

**Gaps vs. current platform:**
- All required cube columns exist in
  `backend/app/transformations/09_cubes/cube_question_summary_overall.sql`
  (verified: `question_no`, `sorting_question_no:280`, `question:281`,
  `correct_answer:285`, `position_number:284`, `grade_average:288`,
  `incorrect_choice_details:297`, `incorrect_details_name:298`,
  `standards:293`, `description:294`, `subject_id:276`,
  `section_instructors:296`).
- Missing dimension-side: `dim_subject.subject_id` is present in repo (used
  in cube), but the public payload `get_assessment_meta` already returns
  these per item.
- Missing helper: `school_logo_url` / `school_name` (covered §3.4).

**Net delta: zero new cube columns required for ord 6.**

### §2.2 Question Summary Report - teacher subtotal (ord 7)

Identical visuals to ord 6 (`20_pages.md:155-180`); the RDL layout adds a
row-grouping level by `dim_item.Section_Instructors`. Same DAX measures, same
M sources.

**Net delta: zero new cube columns. The teacher-subtotal grouping is a
client-side render concern — the data is already keyed by
`section_instructors` (cube_question_summary_overall + dim_item).**

### §2.3 Question Summary Report - header highlights (ord 16)

Visuals (`20_pages.md:345-371`): identical to ord 6 plus one extra
`actionButton`. Header titles are colored (yellow / pink / green) per
`Performance Color Question` (`04_dax_measures.dax:576-592`). The
performance-color tokens are already encoded in the current platform at
`frontend/src/lib/reports/colors.ts` (per §3 of `51_qra_spec.md`).

**Net delta: zero. Pure styling layer; same data feed as ord 6.**

### §2.4 Question Response Analysis (ord 11)

Visuals (`20_pages.md:264-289`): same header + KPI strip + one
`rdlVisual` whose declared fields are listed at `20_pages.md:283-285`:

```
tables: SchoolLogo_Parameter, Titles, cube_question_summary_overall,
        dim_item, dim_subject
fields: dim_item.assessment_date, dim_subject.Assessment_type,
        dim_item.Item_Name, dim_subject.Grade,
        SchoolLogo_Parameter.SchoolLogo_Parameter,
        dim_subject.Subject, cube_question_summary_overall.Subject_ID,
        Titles.H3 - Teachers
```

**Inside-RDL columns** are identical to §1.3 (the 8-column table of
Question_No / Question / %Correct / Correct Answer / Incorrect Choice
Details / Incorrect Details Name / Standards / Description), driven by the
same DAX measures (`__FirstFormatted_*`, `CombineStandardsColumn`,
`CombineDescriptionsColumn`, `questionDax`, `Sorting Question_No`,
`Grade_Average`). See `22_fields_per_page.json:1302-1338` for the explicit
field list.

**Legacy producer:** `cube_Build → Cube_Question_Summary_Overall` block —
`Schoology_py.ipynb:1953-2189`. Notable transformations (verbatim):

```python
# Schoology_py.ipynb:2188
Cube_Question_Summary = Fact_with_Dim.groupBy(
    'uKey','Subject_ID','Question_No', 'Question',
    'Position_Number','Correct_Answer',"Standard").agg(
    F.sum("Points_Possible").alias("Total_Possible_Point"),
    F.sum('Points_Received').alias("Total_Score"),
    (F.sum("Points_Received") / F.sum("Points_Possible")).alias("Grade_Average"),
    ((1 - (F.sum(F.col('Points_Received')) / F.sum(F.col('Points_Possible'))))).alias('Percentage_InCorrect_Answers')
)
```

The per-choice incorrect-choice analysis (`Schoology_py.ipynb:2199-2245`):

```python
# truncated; produces these four output columns:
# Incorrect_Choice_Details, Incorrect_Details_Name,
# Incorrect_Choice_Details_Hash, Incorrect_Details_Name_Hash
ChoicesPerQuestion = FinalResults.groupBy(
    'uKey','Subject_ID', 'Question_No', 'Question',
    "Position_Number", 'Correct_Answer', 'Standard'
).agg(
    F.concat_ws(", ", F.collect_list("Choice_Details")).alias("Incorrect_Choice_Details"),
    F.concat_ws(", ", F.collect_list("Choice_Details_WithName")).alias("Incorrect_Details_Name"),
    …
)
```

**Gaps vs. current platform:** the current SQL
(`09_cubes/cube_question_summary_overall.sql:23-332`) already produces every
column above, with two intentional fixes documented inline:
- Line 60-61: `correct_answer` coalesced to `'n/a'` (matches notebook
  `Schoology_py.ipynb:2026` `Fact_student_submissions.fillna({'Correct_Answer': 'n/a'})`).
- Line 260-272: `id` uses `ukey` (D1 fix) — notebook bug at
  `Schoology_py.ipynb:2173` mistakenly used `Standards` twice.

**Net delta: zero new cube columns. Pure repository-shape work
(`get_questions_overall_for_item(item_id)` already exists at
`cube_repository.py:278`).**

### §2.5 Question Response Analysis by Teacher (ord 12)

Visuals identical to ord 11 (`20_pages.md:291-316`). The RDL inside groups
by `dim_item.Section_Instructors` and adds a per-teacher subtotal block
above each question table.

**Net delta: zero. `section_instructors` is already projected in
`cube_question_summary_overall.section_instructors` (current SQL line 296);
group-by is a frontend concern.**

### §2.6 Question Response Analysis by Standard and Teacher (ord 13)

Visuals identical to ord 11 (`20_pages.md:318-343`). The RDL groups by
both `cube_question_summary_overall.Standards` AND
`dim_item.Section_Instructors`.

**Net delta: zero. Both grouping fields already in cube.**

---

## §3. Cross-cutting findings

### §3.1 Tables consistently used by all 6 reports (shared base for backend exposure)

A single API endpoint per `item_id` would satisfy all six reports. The
returned payload needs:

1. **Assessment meta** (header + KPI strip + slicer caption)
   - `dim_item` row for the item:
     - `item_id`, `item_name`, `assessment_date`, `section_instructors`,
       `subject_id`, `item_type` (current SQL emits all of these).
   - `dim_subject` row for the linked subject:
     - `assessment_type`, `grade`, `session`, `subject` (current SQL
       emits all of these).
2. **KPI strip values** for the item (5 numbers)
   - `cube_school_summary` row keyed (`school_id`, `subject_id`, `item_id`):
     `total_questions`, `total_students`, `total_score`,
     `total_possible_point`, `grade_average`.
3. **Question detail table rows** (the rdlVisual body, 8 columns)
   - `cube_question_summary_overall` filtered to that item's `subject_id`
     (note: cube is keyed by `subject_id`, not directly `item_id`; the
     M expression in `07_power_query.m:69-72` joins back to `dim_item` via
     `Subject_ID` page filter).
   - For all 6 reports the body columns are: `question_no`,
     `sorting_question_no`, `question`, `position_number`, `correct_answer`,
     `grade_average`, `incorrect_choice_details`, `incorrect_details_name`,
     `standards`, `description`, `section_instructors`.

### §3.2 New cube columns we'd need to add

**None.** Every column referenced by the six paginated reports is already
emitted by the current `09_cubes/cube_question_summary_overall.sql` (lines
25-32 INSERT list) or `09_cubes/cube_school_summary.sql`.

The only PBIX-side columns that aren't physical columns are calculated
DAX measures or DAX calc-columns; these are display-formatting concerns:

| PBIX field used by reports                                     | Origin                          | Where it should be computed on current platform                                                    |
|----------------------------------------------------------------|---------------------------------|----------------------------------------------------------------------------------------------------|
| `cube_question_summary_overall.[Sorting Question_No]`          | DAX column `INT([Question_No])` | Repository: `CAST(question_no AS integer)` ordering (current SQL already emits `sorting_question_no`) |
| `cube_question_summary_overall.[Trimmed_Standard]`             | DAX column (drop first two dot-segments) | Already produced by current SQL line 217-220                                                       |
| `Measure.[Grade_Average_Standard_Measure]`                     | DAX `AVERAGE([Grade_Average])`  | API: `AVG(grade_average)` per standard                                                             |
| `Measure.[Incorrect_Grade_Average_Standard_Measure]`           | DAX `1 - [Grade_Average_Standard_Measure]` | API: `1 - AVG(grade_average)`                                                                      |
| `Measure.[Performance Color Standard]`                          | DAX SWITCH on thresholds 0.7/0.8 | Frontend `colors.ts:performanceColor()` (already implemented per `51_qra_spec.md:78`)              |
| `Titles.[H1/H2/H3/Instructor(s):]`                              | DAX literals / CONCATENATEX     | Server-side template strings in the report payload assembly                                        |
| `cube_question_summary_overall.[questionDax]`                  | `FIRSTNONBLANK([Question],1)`   | API: deterministic min(question) per grain                                                         |
| `cube_question_summary_overall.[CombineStandardsColumn]`       | `CONCATENATEX(DISTINCT([Standards]), ", ")` | API: `string_agg(DISTINCT standards, ', ')` per grain                                              |
| `cube_question_summary_overall.[CombineDescriptionsColumn]`    | Picks MAX(Description) for first non-"Other" Standards | Repository — implementable as a post-query select against the same cube                            |
| `cube_question_summary_overall.[__FirstFormatted_correct_]`    | Newline-joined `Position_Number: Correct_Answer` | Frontend or repository: `string_agg(position_number || ': ' || correct_answer, E'\\n' ORDER BY position_number::int)` |
| `cube_question_summary_overall.[__FirstFormatted_Incorrect_Choice_Details]` | Newline-joined Position_Number: Incorrect_Choice_Details, blanked when Grade_Average=1 | Repository — same pattern, with `CASE WHEN grade_average = 1 THEN NULL ELSE …`                     |
| `cube_question_summary_overall.[__FirstFormatted_Incorrect_Details_Name]` | Same pattern as above for the names variant | Repository — same pattern                                                                          |

### §3.3 Schoology vs. cube grain semantics — must-preserve invariants

The notebook publishes `Cube_Question_Summary_Overall` at the grain
`(Subject_ID, Question_No, Position_Number, Correct_Answer, Standards, uKey)`.
The current SQL preserves this grain at
`09_cubes/cube_question_summary_overall.sql:113-138`. Two non-obvious
behaviors to keep:

- **Multi-select "Q12-style" questions** (`Schoology_py.ipynb:2032` chain
  through to `groupBy` with `Points_Possible` / `Points_Received` cast to
  double): the notebook collapses each `(student × question × position)` to
  one row before `SUM(points)/SUM(points)` so that students who choose fewer
  options aren't under-weighted. The current SQL replicates this via the
  `per_student` CTE (lines 127-137) and is documented in
  `docs/audit/fixes/01_q12_multiselect_applied.md`. **Do not collapse this
  back to a single GROUP BY** — that's the bug the docs warn about.

- **Latest-attempt window** (`Schoology_py.ipynb:1991-2000`):
  ```
  Window.partitionBy('Section_NID','Session','Grade','Subject',
                     'Assessment_type','School_ID','User_UID','Item_ID',
                     'Question_ID')
        .orderBy(F.desc('Submission'), F.desc('Total_Seconds'))
  ```
  Replicated in current SQL lines 39-50 with an extra deterministic tiebreak
  on `user_id_ques_id_stand` to stabilize re-runs.

### §3.4 Helper tables — what we'd materialize

| Helper                       | Legacy storage                                  | Current-platform plan                                                                       |
|------------------------------|-------------------------------------------------|---------------------------------------------------------------------------------------------|
| `SchoolLogo_Parameter`       | PBIX parameter `SchoolLogo` (per-tenant)        | Add `school_logo_url` to school config; expose in `assessment.school_logo_url` on the report payload |
| `SchoolName_Parameter`       | PBIX parameter `School_Name` (per-tenant)       | Add `school_name` to school config; expose in `assessment.school_name`                      |
| `Titles.H1/H2/H3/Instructor(s):` | DAX literals + CONCATENATEX over dim_item / dim_subject | Static strings in the React component (current `PageHeader` already does H1/H2)             |
| `Drill Through Report` / `Report Short Name` | Inline base64 JSON inside PBIX | Not needed for paginated reports; only used by Home page slicer                              |

### §3.5 Recommended new repository methods (FastAPI side)

The current `cube_repository.py` already has:
- `get_assessment_meta(item_id)` — `cube_repository.py:1231`
- `get_school_summary_for_item(item_id)` — `:235`
- `get_questions_overall_for_item(item_id)` — `:278`
- `get_incorrect_choices_for_item(item_id)` — `:419`
- `get_standards_for_item(item_id)` — `:463`
- `get_strand_rollup_for_item(...)` — `:500`

All six paginated reports can be served by a single new repository call that
returns one envelope:

```
get_paginated_report_payload(item_id) -> PaginatedReportPayload:
    assessment:           dict   # dim_item ∪ dim_subject ∪ school_name/logo
    kpis:                 dict   # cube_school_summary row → 5 KPI numbers
    questions:            list   # cube_question_summary_overall rows for that
                                  # subject_id, sorted by sorting_question_no
                                  # ─ each row already carries Question_No,
                                  #   Question, Correct_Answer (joined with
                                  #   Position_Number into the
                                  #   __FirstFormatted_correct_ string at the
                                  #   API layer), Incorrect_Choice_Details,
                                  #   Incorrect_Details_Name, Standards,
                                  #   Description, Section_Instructors,
                                  #   Grade_Average
    teacher_groups:       list   # only populated for ord 7, 12, 13:
                                  # list of section_instructors → list of
                                  # question_no above
    standard_groups:      list   # only populated for ord 13:
                                  # list of standards → list of question_no
```

**Signature** (shape only, no implementation):

```
async def get_paginated_report_payload(
    self,
    item_id: str,
    *,
    group_by_teacher: bool = False,
    group_by_standard: bool = False,
) -> Dict[str, Any]:
    ...
```

Wired through a single FastAPI endpoint:

```
GET /api/v1/reports/paginated/{report_kind}/{item_id}
    where report_kind ∈ {
        "question_summary",
        "question_summary_teacher",
        "question_summary_color",
        "question_response_analysis",
        "question_response_analysis_teacher",
        "question_response_analysis_standard_teacher",
    }
```

The `report_kind` toggles `group_by_teacher` / `group_by_standard` flags and
selects the React component to render.

### §3.6 Tables NOT used by the 6 paginated reports

To save research time later: these PBIX tables exist but feed only
non-paginated views — do **not** need to be exposed for the 6 reports.

- `cube_users_summary` (note trailing `s`): referenced only by the
  redacted ord-17 page (`20_pages.md:397-399`). Not in `03_schema.csv`
  — likely a legacy alias / removed table.
- `cube_user_summary` (no trailing s): produced at
  `Schoology_py.ipynb:2278-2473`; used only by Year-To-Date interactive
  pages (not the 6 paginated reports).
- `cube_grade_summary` / `Cube_Grade_measure` (notebook 1322-1344):
  feeds Year-To-Date longitudinal pages.
- `cube_overallperformance_summary` (notebook 2249-2274): feeds non-
  paginated drill-throughs.
- `dim_strand` / `dim_standard.Strand`: used by Strand/Standard summary
  pages (ord 14/15), not the 6 paginated reports — though
  `dim_standard.description` IS needed (already in cube join).
- `Cube_QuestionIncorrectChoice_Summary` (notebook 1772-1799): feeds the
  Incorrect Answer Details page (ord 5), not directly the 6 paginated
  reports (though its `Total_Score` is what backs the `Score` KPI strip
  value — already covered by `cube_school_summary.total_score` per §1.2).

---

## §4. Where things definitely are NOT

For completeness, claims explicitly ruled out by grep:

- **No SQL views / stored procedures in legacy** that produce the cubes.
  The cubes are parquet emitted by Spark; Synapse Serverless reads them
  via external-table CREATE statements (`oea.add_to_lake_db(...)` calls in
  `Schoology_py.ipynb:1370, 1411, …`). There is no `.sql` file in
  `gains legacy/OEA/modules/module_catalog/Schoology_Analytics/`.
- **No .NET / C# code path** for paginated reports.
  `EdvanceLearning/services/reporting/`, `EdvanceLearning/GainsAi/`,
  `EdvanceLearning/apps/EdvanceLS.Gains/` contain LMS, GenAI, and gateway
  code; none reference `cube_*` table names. (Verified by listing
  `EdvanceLearning/services/reporting` and looking for `cube_` mentions —
  zero hits.)
- **No `cube_Build` outside the Schoology notebook.** Only one match for
  `def cube_Build` across `gains legacy/OEA/modules/module_catalog/`,
  located at `Schoology_py.ipynb:1322`.
- **No power-query M code outside the PBIX.** All M expressions live in
  `data/_pbix_extract/07_power_query.m`; the legacy tree contains no
  `*.pq` / `*.m` files.

---

## §5. Reference — the cube_Build call graph (Spark notebook)

For navigation, the seven cube definitions inside the single
`cube_Build` method at `Schoology_py.ipynb:1322-2473`:

| Cube                                  | Notebook line span (1-based)            | Output path                                                 |
|---------------------------------------|----------------------------------------|-------------------------------------------------------------|
| `Cube_Grade_Summary`                  | `1336-1364`                            | `stage3/Published/schoology/v{ver}/Cube_Grade_Summary`      |
| `Cube_School_Summary`                 | `1365-1391`                            | `…/Cube_School_Summary`                                     |
| `Cube_Standard_Summary`               | `1392-1414`                            | `…/Cube_Standard_Summary`                                   |
| `Cube_Question_Summary`               | `1581-1771`                            | `…/Cube_Question_Summary`                                   |
| `Cube_QuestionIncorrectChoice_Summary`| `1772-1799`                            | `…/Cube_QuestionIncorrectChoice_Summary`                    |
| `Cube_Question_Summary_Overall`       | `1953-2189`                            | `…/Cube_Question_Summary_Overall`                           |
| `Cube_OverallPerformance_Summary`     | `2188-2274`                            | `…/Cube_OverallPerformance_Summary`                         |
| `Cube_User_Summary` (paginated)       | `2278-2473`                            | `…/Cube_User_Summary`                                       |

Of these, **only `Cube_Question_Summary_Overall` and `Cube_School_Summary`
are required for the six paginated reports** (§3.1).

---

## §6. Frontend / current-platform anchors (for cross-reference)

- Existing QRA implementation: `frontend/src/app/app/reports/question-response-analysis/page.tsx`.
- Existing service shape: `backend/app/services/report_service.py` → `build_question_response_analysis(item_id)`.
- Existing cube SQL: `backend/app/transformations/09_cubes/cube_question_summary_overall.sql`.
- Existing color tokens: `frontend/src/lib/reports/colors.ts` (matches PBIX
  thresholds 0.7 / 0.8 per `04_dax_measures.dax:576-592` and `:250-266`).
- Existing repository methods (all already in place):
  `cube_repository.py:235` (school summary), `:278` (questions overall),
  `:419` (incorrect choices), `:463` (standards), `:1231` (assessment
  meta).

Net implementation cost of the 6 paginated reports beyond what already
exists: **render-layer-only** — six React components plus one new repo
method `get_paginated_report_payload(item_id, group_by_teacher,
group_by_standard)` that orchestrates the existing cube reads, plus the two
school-tenant strings (`school_name`, `school_logo_url`) wired through the
assessment payload.
