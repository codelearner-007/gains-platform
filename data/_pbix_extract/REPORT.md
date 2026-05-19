# Athenian PBIX Exploration — Full Report

> Source: `data/Assessment Analysis Dashboard.pbix` (134 MB on disk, 205 MB uncompressed model).
> Extraction tool: `pbixray` (Python, no Power BI Desktop required).
> All artifacts in this folder are the source of truth — re-run `_extract.py` + `_layout.py` to regenerate.

---

## 1. File Anatomy

A PBIX is a ZIP container with these parts:

| Part | Bytes | What it is |
|---|---:|---|
| `DataModel` | 140 MB | Analysis Services Tabular model — binary, holds all imported data + DAX |
| `Report/Layout` | 3 MB | UTF-16 LE JSON. Pages, visual containers, slicers, bookmarks, themes |
| `DiagramLayout` | 8 KB | Visual position of model diagram (cosmetic) |
| `Report/LinguisticSchema` | 5 KB | Q&A natural-language schema |
| `Connections` | 203 B | Data source registration |
| `Report/StaticResources/RegisteredResources/*.png` | ~500 KB | Theme/icon assets (chart sparkline icons, `Default_Owl_Logo*.png`, etc.) |
| `Settings`, `Metadata`, `Version`, `[Content_Types].xml` | small | Power BI bookkeeping |

Build hint: many `Default_Owl_Logo*.png` files in StaticResources — the original report was scaffolded from the Microsoft "Owl"/"AdventureWorks-style" Power BI template.

---

## 2. Data Source

The single critical line in `Connections` and confirmed by every M query:

```
Sql.Database("syn-oea-prodtest2-ondemand.sql.azuresynapse.net", "ldb_dev_s3_schoology_v0p1")
```

**The PBIX consumes pre-cubed data from Azure Synapse Serverless SQL.** It does **not** read the Schoology CSVs directly. The Synapse `Schoology_py.ipynb` notebook is what turns the CSVs into the `cube_*` tables that this report binds to.

### Per-tenant parameterization (M parameters, not DAX RLS)

The PBIX ships with four query parameters:

| Parameter | Used in | Purpose |
|---|---|---|
| `SchoolID` | `dim_item`, `dim_subject` M filters | Restrict every table to one school |
| `School_Name` | `SchoolName_Parameter` | Display in titles |
| `SchoolLogo` | `SchoolLogo_Parameter` | Image in headers |
| `FilterExpression` | `dim_item` M filter | Pipe-separated `Item_Name` substrings to **exclude** (e.g., `Practice|Sample|Demo`) |

The dim_item M body shows the exclusion logic:
```m
not List.AnyTrue(
    List.Transform(
        Text.Split(if FilterExpression = null then "|" else FilterExpression, " | "),
        (x) => Text.Contains([Item_Name], x, Comparer.OrdinalIgnoreCase)
    )
)
```

> ### 🚩 Important divergence from the canonical doc
> The canonical Tech Doc claims RLS is enforced via a Roles table + `USERPRINCIPALNAME()` DAX. **That is not what this PBIX does.** Tenant isolation is achieved by **cloning the PBIX per school** with different M parameter values baked in. There is no Roles table in this PBIX.
>
> For our rebuild this is *good news* — we don't have to replicate complex DAX RLS. We filter by `school_id` at the API/RLS layer (Supabase RLS does this trivially in one policy).

---

## 3. Data Model — 18 Tables

### 3.1 Cubes (5 — all loaded from Synapse `dbo.cube_*`)

| Table | Rows in snapshot | Purpose | Key cols |
|---|---:|---|---|
| `cube_school_summary` | 16,747 | School-level rollup per (school × subject × item) | School_ID, Subject_ID, Item_ID, Total_Questions, Total_Standards, Total_Students, Total_Possible_Point, Total_Score, Grade_Average |
| `cube_grade_summary` | 16,747 | Grade-level (per item) | School_ID, Subject_ID, Item_ID, Grade_Average, Percentage_InCorrect_Answers, Grade_Min, Grade_Max |
| `cube_standard_summary` | 62,375 | Per-standard rollup | Strand_ID, Identifier, Total_Questions, Total_Standards, Total_Possible_Point, Total_Score, Grade_Average, Item_ID |
| `cube_question_summary` | 125,775 | Per-question per-section per-assessment (rich, with Section_Instructors, TeacherName_Hash, Incorrect_Choice_Details) | Question_ID, Item_ID, Subject_ID, Question_No, Question, Correct_Answer, Total_Possible_Point, Grade_Average, Standards, Identifier, Qkey/Ukey |
| `cube_question_summary_overall` | 72,968 | Per-question across sections (collapsed) — **the main table for question-level reports** | Question_No, Question, Correct_Answer, Grade_Average, Standards, Description (HTML-cleaned), Position_Number, Trimmed_Standard (calc col), Sorting Question_No (calc col) |
| `cube_questionincorrectchoice_summary` | 440,811 | Per-question × per-(incorrect)-answer-option distractor analysis | Question_ID, Answer_Submission, Total_Student, Total_Possible_Point, Total_Score, Grade_Average |

### 3.2 Facts (1 — DirectQuery, not embedded)

| Table | Rows | Notes |
|---|---:|---|
| `fact_student_submission` | 0 (DirectQuery) | One row per student × question. Loaded live from Synapse on each report query. Has 35 cols: User_UID, User_Role_ID, School_ID, Course_NID, Section_NID, Item_ID, Question_ID, Submission_Grade, Answer_Submission, Correct_Answer, Points_Received/Possible, Grade_ID, Assessment_ID, Subject_ID, strand_ID, User_Name, Standard… |

### 3.3 Dimensions (5)

| Table | Rows | Notes |
|---|---:|---|
| `dim_item` | 3,758 | Per-assessment metadata. Filtered by `[School_ID] = SchoolID` parameter and the `FilterExpression` exclusion |
| `dim_subject` | 2,034 | Subject × Grade × Assessment_type × Session × Item_Name. Has calc cols `ShowHistorySubject` (Grade 6/7 History → World/US History) and `Grade_no` (last char of Grade) |
| `dim_question_data` | 0 (DirectQuery) | All question-level metadata, fed live |
| `dim_standard` | 7,958 | Academic standards. Has `Cognitive_Complexity_Rating`, `Direct_Link`, `Schoology_Standard`, `cPalms_Standard`, `Strand`, HTML-cleaned `description` |
| `dim_strand` | 7,071 | Strand-level rollup |

### 3.4 Helper / parameter / "measure-only" tables (7)

| Table | Rows | Notes |
|---|---:|---|
| `Drill Through Report` | 12 | Page-routing config (Page → Report Name → Category → Sort) — drives drill-through targets. Hardcoded inside the PBIX as a base64-deflated table |
| `Report Short Name` | 2 | Same shape, smaller subset |
| `SchoolName_Parameter` | 1 | Just exposes `School_Name` parameter as a queryable scalar |
| `SchoolLogo_Parameter` | 1 | Same for `SchoolLogo` |
| `Measure` | 1 | Empty placeholder — holds 30+ DAX measures. PBI convention: organize measures by domain in named "tables" |
| `Titles` | 1 | Empty placeholder — holds the H1/H2/H3 dynamic title measures |

### 3.5 Relationships (14)

```
                    dim_subject
                        ▲
                        │ M:1 (Subject_ID)
                    dim_item ─── M:1 (Item_ID) ◄─── cube_school_summary
                                              ◄─── cube_grade_summary
                                              ◄─── cube_question_summary
                                              ◄─── cube_standard_summary

   dim_standard ◄─ M:M (Identifier=Identifier) ─► dim_strand
                                                     ▲ M:M (inactive)
   cube_standard_summary ── M:M ──┐                  │
   cube_question_summary_overall ─┼─► dim_standard   │
                                  │   (Schoology_Standard)
                                  │                  │
                                  └────► via Identifier → dim_strand

   cube_question_summary_overall ◄── M:M (Ukey=uKey) ──► cube_question_summary
   cube_questionincorrectchoice_summary ◄── M:M (Question_ID) ──► cube_question_summary
   fact_student_submission ◄── M:M (Question_ID, Answer_Submission inactive) ──► cube_questionincorrectchoice_summary

   Report Short Name (Page) ◄── 1:1 ──► Drill Through Report
```

Notes:
- 8 of 14 relationships are **bidirectional** (Both filter direction) — Power BI's flag for "we couldn't make a clean star schema." We can simplify in Postgres.
- 5 are **M:M** — same signal. The `Ukey`/`Qkey` columns are 64-char hash keys (verified in stats: cardinality 53,613 for Ukey in cube_question_summary). The Schoology pipeline generates these via UUID-from-concat in the `Schoology_py.ipynb` notebook.
- 2 relationships are **inactive** (cube_standard_summary→dim_strand on Strand_ID; fact_student_submission→cube_questionincorrectchoice_summary on Answer_Submission). They exist for `USERELATIONSHIP()` calls in DAX.

---

## 4. Power Query M (18 queries)

All cubes/dims load with the same boilerplate:
```m
Source = Sql.Database("syn-oea-prodtest2-ondemand.sql.azuresynapse.net", "ldb_dev_s3_schoology_v0p1"),
dbo_X = Source{[Schema="dbo", Item="X"]}[Data]
```

Notable customizations:
- `dim_item` → filtered by `SchoolID` + `FilterExpression` exclusion + cast `assessment_date` to `type date`.
- `dim_subject` → filtered by `SchoolID`, adds `GradeSort` (Grade K → Grade 0 for sort order), excludes two specific Subject_ID hashes (`6dc2c0d6…` and `639b701a…` — likely "Other" / null-subject buckets).
- `cube_question_summary_overall` → `Description` HTML-stripped via `Html.Table` + `Text.Combine`; rows where `Question_No is null` filtered out.
- `cube_questionincorrectchoice_summary` → rows where `Answer_Submission is null` filtered out.
- `dim_standard` → cleans `description` HTML the same way.
- `Drill Through Report` and `Report Short Name` → bake their full rows into a base64-deflated `Json.Document` literal inside the query (no source connection).

---

## 5. DAX Measures (62) — Categorized

Full source is in `04_dax_measures.dax`. Categorized:

### 5.1 Core averages & rollups (the "actual numbers" we have to match)
- `Grade_Average_Standard_Measure` = `AVERAGE('cube_question_summary_overall'[Grade_Average])`
- `Grade Average` = same
- `Grade Average2` = same, formatted `"0.0%"`
- `% Correct Answer` = `AVERAGE('cube_question_summary_overall'[Grade_Average])`
- `Grade_Average_Strand_Measure` = same wrapped in `CALCULATE`
- `subjectAvg` = `IF(ISBLANK(AVG(cube_standard_summary[Grade_Average])), 0, AVG(...))`
- `Grade Min` / `Grade Max` = `MINX/MAXX(VALUES([Question_No]), CALCULATE(AVG([Grade_Average])))`
- `Incorrect_Grade_Average_Standard_Measure` = `1 - [Grade_Average_Standard_Measure]`

### 5.2 Counts
- `Total Student` = `SUMX(SUMMARIZE(cube_school_summary, Item_ID, "x", MAX([Total_Students])), [x])`
- `Total Question` = `DISTINCTCOUNT(cube_question_summary_overall[Question_No])`
- `Total Standard` = `DISTINCTCOUNT(cube_question_summary_overall[Standards])`
- `Total Possible Point` = `SUMX(SUMMARIZE(cube_question_summary, Question_ID, "x", MAX([Total_Possible_Point])), [x])`
- `Possible Point` (per-incorrect-choice variant) — same shape on `cube_questionincorrectchoice_summary`
- `Total Question Standard` / `Total Question Strand` / `Total Standard by Strand` — same SUMMARIZE-over-distinct pattern
- `# of students` = `DISTINCTCOUNT(fact_student_submission[User_UID])`
- `Total Incorrect Choices` = `DISTINCTCOUNT(fact_student_submission[Answer_Submission])`

### 5.3 Conditional formatting (traffic-light colors)
**Universal threshold across the report: `< 0.7 = pink (#FFCCFF)`, `0.7–0.8 = Yellow`, `≥ 0.8 = green (#00FF06)`.**
Variants: `Performance Color`, `Performance Color Strand`, `Performance Color Standard`, `Performance Color Standard2`, `Performance_Color_Standard 3`, `Performance Color Question`, `Performance Color_subject` — all the same SWITCH(TRUE(),…) over a different aggregation source.

### 5.4 SVG inline visualizations (clever DAX)
- `_Data Bar - Grade Average` — emits a `<svg>` data-URL string with a coloured bar (width = grade_avg × 250px), a dashed marker line at the ALLSELECTED average, and percentage text. Uses the Performance Color measure for fill. **This is one custom visual we'll need to recreate (or replace with a real React Recharts component).**
- `Treemap Color` — pseudo-random color from hashing the first 3 chars of the Strand string into a light pastel hex. Used as the `dataColors` source in the strand treemap.

### 5.5 Title/Header text composition (in `Titles` table — 12 measures)
- `H1 - Report Header` = `"Grade Performance by Strand"` (literal)
- `H1 - Longitudinal` = `"Paginated PDF Report |"`
- `__Title` = `"Assessments Dashboard"`
- `H2 - Course and Unit` = concatenates Grade + Item_Name from selected slicers
- `H2 - Assessment Type` = trims "  " → " " in selected dim_subject[Assessment_type] then concatenates
- `H2 - Question Details` = `"Incorrect Answer Details"`
- `H3 - Total Students` = `"Total Students: " & [Total Student]`
- `H3 - # of questions`, `H3 - # of standards`, `H3 - Grade Average` — same shape
- `Instructor(s):` = newline-separated dim_Item[Section_Instructors]

### 5.6 Question-level formatters (in `cube_question_summary_overall` table)
The complex multi-paragraph ones we need for **Question Response Analysis**:
- `__FirstFormatted_correct_` — emits multi-line `"1: A\n2: B\n3: C"` from Position_Number + Correct_Answer, sorted ascending. Suppresses if Grade_Average == 100%.
- `__FirstFormatted_Incorrect_Choice_Details` — same shape, suppresses if Grade_Average == 100%.
- `__FirstFormatted_Incorrect_Details_Name` — concatenates student names per incorrect answer, multi-line.
- `Incorrect Choice details` — picks the top-1 most-chosen incorrect answer with `"35.7% chose [b. b]"` formatting.
- `Incorrect Details Name` — for each `Answer_Submission`, lists which students chose it.
- `CombineStandardsColumn` / `concateIncorrect_Choice_Details` / `concateIncorrect_Details_Name` — aggregator helpers.
- `CombineDescriptionsColumn` — picks the description for the first non-`"Other"` standard.
- `questionDax` = `FIRSTNONBLANK(Question, 1)` — used as the question-text in tables.
- `FormattedString` — `<` → `<img width='30%' src='`, `>` → `' />` — converts URL-in-angle-brackets question text into HTML images (questions with screenshots).

### 5.7 Misc
- `# of Students (Sum of Row-wise)` — `SUMX(VALUES(answer_submission), DISTINCTCOUNT(User_UID))`
- `% of All Answers` — share of points-possible across all submissions
- `% Correct Answer By Incorrect Choice` = `DIVIDE([Possible Point], [Total Possible Point])`
- `Score` = `SUM(cube_questionincorrectchoice_summary[Total_Score])`
- `Measure` (in cube_questionincorrectchoice_summary) — % share of possible points
- `Drillthrough Selection` = `SELECTEDVALUE('Drill Through Report'[Page])`
- `Measure_Standard` / `Measure_Standards` — `FIRSTNONBLANK` accessors
- `test`, `blank` — dev/empty leftovers

### 5.8 Calculated columns (4)
- `dim_subject[ShowHistorySubject]` — Grade 6 History → "World History", Grade 7 History → "US History"
- `dim_subject[Grade_no]` = `RIGHT([Grade], 1)` — last char ("Grade 5" → "5")
- `cube_question_summary_overall[Sorting Question_No]` = `INT([Question_No])` — for proper numeric sort
- `cube_question_summary_overall[Trimmed_Standard]` — strips first 2 dot-segments off a standard like `MATH.5.NBT.2` → `NBT.2`

---

## 6. Pages & Visuals — 20 Pages

> Full per-visual JSON in `20_pages.json`; markdown summary in `20_pages.md`; per-page field map in `22_fields_per_page.json`.

| # | Page | Visuals | Status | Tables actually bound |
|---|---|---:|---|---|
| 1 | Standard Summary | 23 | working (paginated) | dim_standard, dim_subject, dim_item, Measure |
| 2 | Strand Summary | 24 | working (paginated) | dim_standard, dim_strand, Measure |
| 3 | QuestionView | 2 | drill-through anchor | small |
| 4 | Question Summary Report | 8 | working | dim_subject, dim_item, cube_question_summary_overall |
| 5 | Question Summary Report - teacher subtotal | 8 | working | same + Section_Instructors |
| 6 | Year To Date - Longitudinal Report | 8 | working | cube_question_summary_overall |
| 7 | Year To Date - Longitudinal Report 2 | 8 | working | same |
| 8 | Year To Date - Longitudinal Report 3 | 9 | working | same |
| 9 | **Question Response Analysis** | 8 | working (paginated) | dim_item, dim_subject, cube_question_summary_overall, Titles, SchoolLogo |
| 10 | Question Response Analysis by Teacher | 8 | working variant | + Section_Instructors |
| 11 | Question Response Analysis by Standard and Teacher | 8 | working variant | + Strand |
| 12 | Question Summary Report - header highlights | 9 | working | same as #4 |
| 13 | Question Summary Report redacted | 9 | working — uses *_Hash columns | sandbox/pseudonymized |
| 14 | Question Response Analysis redacted | 8 | working — uses *_Hash columns | sandbox/pseudonymized |
| 15 | **Home** | 73 | ⚠️ MOSTLY BROKEN — uses ghost tables | see §6.1 |
| 16 | **Standards Deep Dive interactive** | 39 | working (interactive) | cube_standard_summary, dim_standard, dim_strand, dim_subject, Measure |
| 17 | **Question Response Analysis Interactive** | 28 | working (interactive) | cube_question_summary_overall, dim_standard, dim_subject, Measure |
| 18 | Selected Assessment | 1 | drill-through anchor | tiny |
| 19 | Selected Strand | 1 | drill-through anchor | tiny |
| 20 | Incorrect Answer Details | 17 | drill-through page | cube_questionincorrectchoice_summary, fact_student_submission |

### 6.1 The Home page is broken template scaffolding

Out of 82 distinct field references on the Home page, half point at **tables that don't exist in the model**:
- `Sales Measures.Rib_Ele_01..04`, `Rib_green_01..04`, `Rib_pink_01..04`, `Rib_yellow_01..04` (16 refs!)
- `Products.Color`, `Products.Color_sort`, `Products.Product Category`
- `Date.Month`
- `Assessments.Grade`, `Assessments.Subject`
- `Color.Color`
- `Clustered chart.Clustered columns`, `Clustered chart.Legend`
- `Drillthrough_Pages.*`
- `Query1._Data Bar - Grade Average`
- `Key Measures.Grae Avg` (typo)
- `Questions Data.Item Name`

These are ghost references inherited from the Power BI **template** the report was scaffolded from. In the live Power BI service these visuals would render as errors / blanks. **The Home page is dead.**

The same template residue contaminates other pages too — every reference to `Key Measures.Total Questions` (plural), `Standards.Standard`, `Student Submissions.*`, `Sum(Student Submissions.Points Possible)` is a ghost reference. The model has `Measure` not `Key Measures`, `dim_standard` not `Standards`, `fact_student_submission` not `Student Submissions`. Visuals using these would also fail/blank.

What this means: the **paginated** pages (1–14, 18–20) are healthy, but the two flashy **Interactive** pages (#16, #17) are the ones with both real working visuals AND modern UX. Those are the ones to copy.

### 6.2 Per-page field reference frequency (live model only)

After filtering out ghost tables, the most-used real fields globally:
| Refs | Field |
|---:|---|
| 12 | `Measure.Grade_Average_Standard_Measure` |
| 13 | `dim_standard.cPalms_Standard` |
| 13 | `dim_subject.Subject` |
| 13 | `dim_subject.Grade` |
| 14 | `Titles.H2 - Assessment Type` |
| 13 | `Titles.H2 Course and Unit` |

---

## 7. Pilot Reports — Deep Dive

### 7.1 Question Response Analysis Interactive (28 visuals)

**Tables bound:** Measure, cube_question_summary_overall, dim_standard, dim_subject, Titles, SchoolLogo_Parameter

**KPI cards (top strip):**
- Overall Lowest % — uses `Measure.Grade Min`
- Overall Highest % — `Measure.Grade Max`
- Grade Average — `Measure.Grade_Average_Standard_Measure`
- Number of Standards — `Measure.Total Standard`
- Number of Questions — `Measure.Total Question`
- Total Students — `Measure.Total Student`

**Body visuals:**
- `tableEx "Correct % by Standards"` — table over Measure × cube_question_summary_overall
- `tableEx` — full per-question table from cube_question_summary_overall (uses `__FirstFormatted_correct_`, `__FirstFormatted_Incorrect_Choice_Details`, `__FirstFormatted_Incorrect_Details_Name`, `CombineStandardsColumn`, `CombineDescriptionsColumn`, `questionDax`)
- `tableEx "Correct % by Strands"` — Measure × dim_standard
- `slicer` over Standards
- `treemap` of standards
- `funnel "Standards by # of Questions"`
- `barChart` + `clusteredBarChart` + `hundredPercentStackedBarChart` "Correct and Incorrect % by Standards"
- 2 `actionButton`s for navigation
- 4 `multiRowCard`s for instructor and dynamic titles

### 7.2 Standards Deep Dive Interactive (39 visuals)

**Tables bound:** Measure, cube_standard_summary, dim_standard, dim_strand, dim_subject, Titles, SchoolLogo_Parameter

**KPI cards (top strip):** same set as 7.1 plus
- Overall Lowest % / Highest %

**Body visuals:**
- `tableEx` over Measure × dim_standard × Standards-related-measures
- `funnel "Standards by # of Questions"` (×2)
- `treemap "# of Standards by Strand"` — uses `Measure.Treemap Color`
- `barChart` + `clusteredBarChart` "Correct and Incorrect % by Standards"
- `hundredPercentStackedBarChart "Correct and Incorrect % by Standards"` (×3 — different drill-down levels)
- 2 `charticulatorVisualCommunity_VIEW` — custom Charticulator visuals (we'll replicate as Recharts)
- 2 `actionButton`s + textboxes for sub-headers

### 7.3 Why these two are the right pair

- **Same source tables** — both lean on `cube_question_summary_overall`/`cube_standard_summary` + `dim_standard`/`dim_strand`/`dim_subject` + the `Measure` DAX bag. The dbt models we build for one cover ~80% of the other.
- **Same KPI strip** (Grade Avg, # Questions, # Standards, Total Students, Lowest/Highest %) — one React `<KpiStrip>` component reused.
- **Same color thresholds** (70%/80% pink/yellow/green) — one design token reused.
- **Different lens** — one drills into questions (which questions tripped up students, what wrong answers were popular); the other drills into standards/strands (which standards/strands the school struggles with). Together they prove the per-tenant filter, the cube layer, the API, and two distinct visualization patterns end-to-end.

---

## 8. What This Means for Our Rebuild

### 8.1 Pipeline shape

The PBIX confirms the canonical pipeline architecture:

```
CSV (Blob)  ─────►  Synapse Spark + Delta cubes  ─────►  PBIX  ─────►  PBI Service workspace per school
   ↑                       ↑                              ↑                   ↑
   what we have         to translate                 to translate         not needed
   in data/Athenian/    to dbt + Postgres            to Next.js + React   (we use Supabase Auth)
```

In our stack:
1. **Ingestion (Python + FastAPI)** — read 3 CSV types from `data/Athenian/{path}/`, parse, normalize, insert into Postgres `raw_*` tables.
2. **Transformation (dbt-postgres)** — port `Schoology_py.ipynb`'s `dim_*` and `fact_student_submission` builds into staging models, then build the `cube_*` tables as marts.
3. **API (FastAPI)** — endpoints that return the same shape the PBIX cubes expose.
4. **UI (Next.js + React + Recharts)** — replicate the two interactive pages' visuals + the KPI strip.

### 8.2 Postgres schema we need

Map directly from the PBIX schema (with light cleanup):

```
-- Reference / per-school (RLS keyed)
schools(school_id, name, logo_url, item_filter_expression)

-- Dimensions
dim_subject(subject_id, school_id, subject, assessment_type, grade, session, item_name, …)
dim_item(item_id, subject_id, school_id, item_name, item_type, section_name, section_instructors, assessment_date)
dim_standard(identifier, schoology_standard, strand, subject, description, cluster, cognitive_complexity_rating, direct_link, …)
dim_strand(identifier, strand, strand_id)
dim_question_data(question_id, item_id, …)  -- many cols, mostly direct from CSV

-- Fact (long format, one row per student × question)
fact_student_submission(
  user_id_ques_id PK,
  user_uid, user_role_id, user_name, school_id, course_nid,
  section_nid, section_code, item_id, item_name, question_id,
  first_access, latest_attempt, total_time, submission_grade,
  submission, session, assessment_type, subject, grade, section,
  position_number, sub_question, answer_submission, correct_answer,
  points_received, points_possible,
  grade_id, assessment_id, subject_id, strand_id, standard
)

-- Cubes (computed via dbt; refreshable)
cube_school_summary(school_id, subject_id, item_id, total_questions, total_standards, total_students, total_possible_point, total_score, grade_average, percentage_incorrect_answers)
cube_grade_summary(school_id, subject_id, item_id, grade_average, percentage_incorrect_answers, grade_min, grade_max)
cube_standard_summary(strand_id, identifier, total_questions, total_standards, total_possible_point, total_score, grade_average, percentage_incorrect_answers, item_id)
cube_question_summary(question_id, item_id, subject_id, school_id, question_no, question, correct_answer, total_possible_point, grade_average, standards, identifier, qkey, ukey, position_number, …)
cube_question_summary_overall(question_no, question, correct_answer, total_possible_point, grade_average, standards, description_clean, position_number, sorting_question_no, trimmed_standard, ukey)
cube_questionincorrectchoice_summary(question_id, answer_submission, total_student, total_possible_point, total_score, grade_average, percentage_incorrect_answers)
```

### 8.3 DAX measures we have to translate

For the two pilot reports, the must-translate set is small (~15):
- `Grade_Average_Standard_Measure` → SQL: `AVG(grade_average)` over the right grain
- `Grade Min` / `Grade Max` → window aggregates over question_no
- `Total Question` → `count(distinct question_no)`
- `Total Standard` → `count(distinct standards)`
- `Total Possible Point` → `sum of max(total_possible_point) per question_id`
- `Total Student` → `sum of max(total_students) per item_id`
- `Possible Point` / `Score` → straight sums
- `% Correct Answer` / `% Correct Answer By Incorrect Choice` → simple division
- `__FirstFormatted_*` (3 multi-line formatters) → can be done in Postgres (`string_agg` + sort) OR in the API layer in Python — easier in Python.
- `Performance Color` (and variants) → trivial SWITCH at the UI level (no DB needed).
- `Treemap Color` → keep the hash-based pseudo-random pastel logic in JS.
- `_Data Bar - Grade Average` → drop entirely; recreate as a real React component instead of inline SVG.

The dropped/skipped measures (Sales rib templates, ghost-table refs) cost us nothing.

### 8.4 What's "data infrastructure" that doesn't translate

- The 14 PBIX relationships → become foreign keys + dbt `relationships` tests
- 11 of them are `Both`-direction or `M:M` because of the Synapse star-schema legacy → we can simplify to `M:1` in Postgres (validate by reproducing same totals)
- `Drill Through Report` page-routing table → becomes Next.js routes, not a database table
- `Report Short Name` page metadata → same, just a JSON in the frontend
- `SchoolID`/`School_Name`/`SchoolLogo`/`FilterExpression` PBIX parameters → Supabase row in `schools` table + RLS policy

### 8.5 Open questions

1. **`item_filter_expression`** — what values does Athenian actually ship with? The M code defaults to `"|"` (i.e., exclude nothing). If they exclude e.g. `"Practice|Sample"`, we need that string as data in our `schools` row.
2. **Standards data** — `dim_standard` (7,958 rows) is in the PBIX as embedded data. We need to port that as seed data, or accept the canonical doc note that the CASE Network feed is dead and re-curate ourselves.
3. **The `fact_student_submission` shape** — the PBIX uses DirectQuery; we have 35 columns to support. The CSV `Student-Submissions-*.csv` we have should map to most of these — we'll verify col-by-col when we build the ingest job.
4. **Pseudonymized variants** — `*_Hash` columns and `redacted` pages are out of MVP scope, can be deferred.
5. **The Athenian academic-year currently in the data** — the snapshot in the PBIX shows StructureModifiedTime up to 2026-03-05, so the cubes were last rebuilt then. Our scraper run pulled academic year `2025-26`, due window 2026-04-21 → 2026-05-05. That's after the PBIX snapshot, so our CSVs are NEWER data than the PBIX cubes. For sempy validation we need to either (a) regenerate the PBIX cubes against fresh data, or (b) restrict our CSV intake to a date range that matches the PBIX snapshot.

---

## 9. Files in `data/_pbix_extract/`

| File | Purpose |
|---|---|
| `_extract.py` | Re-runnable: opens PBIX with pbixray, dumps everything below |
| `_layout.py` | Re-runnable: parses `Report/Layout` JSON |
| `01_metadata.json` | Power BI build settings |
| `02_tables.json` | List of 18 tables |
| `03_schema.csv` | All 221 columns with types |
| `04_dax_measures.csv` / `.dax` | 62 measures, full source |
| `05_dax_columns.csv` / `.dax` | 4 calculated columns |
| `06_dax_tables.csv` | 0 calculated tables |
| `07_power_query.csv` / `.m` | 18 M queries |
| `08_relationships.csv` | 14 relationships, cardinality, filter direction |
| `09_statistics.csv` | Per-column cardinality, dictionary size, modified time |
| `10_table_heads.json` | Top-5 row sample per table |
| `11_model_size.txt` | 205 MB uncompressed |
| `tables/<TableName>.head.csv` | First 5 rows of each table as CSV |
| `20_pages.json` / `.md` | All 20 pages, all visuals, types, fields |
| `21_top_fields.md` | Field/measure usage frequency across the report |
| `22_fields_per_page.json` | Per-page field/measure usage |
| `_layout.full.json` | Full Layout JSON (3 MB, regenerated) |
| `REPORT.md` | This file |

---

*Generated 2026-05-05 from `data/Assessment Analysis Dashboard.pbix` using pbixray + custom Layout JSON parser. To regenerate, run `python _extract.py && python _layout.py` from this directory.*
