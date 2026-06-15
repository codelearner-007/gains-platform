# Question Response Analysis — Paginated Variants (ord 11 / 12 / 13)

> Reverse-engineered spec for the **three SSRS-style paginated** "Question
> Response Analysis" pages embedded inside the PBIX. These are the printable
> PDF siblings of the interactive QRA page we already ship at
> `frontend/src/app/app/reports/question-response-analysis`
> (`51_qra_spec.md`). Each paginated page in the PBIX is an outer Power BI
> shell — header strip + KPI multiRowCard + a single full-width
> **`rdlVisual`** that pulls in a server-side RDL/SSRS report. The RDL body
> defines the actual question table, row groupings and "Standard
> Average / Section Instructor" subtotal bands.
>
> The Power BI shell layout is identical across all three pages (same 7
> chrome visuals at the same coordinates); the **only delta is the embedded
> RDL report ID and its parameter map** (and one extra page-level filter on
> `cube_user_summary.Item_Name`). The RDL bodies themselves are not in the
> PBIX file — they live on the Power BI service workspace
> `8215049c-ebd6-4a9b-bb98-5b5fdb7d3da4`. This document therefore reconstructs
> them from the PBIX wiring + the rendered PDFs in
> `data/sample reports/Paginated - Question Response Analysis*.pdf`.
>
> **Sources used:**
> - `data/_pbix_extract/_layout.full.json` (full visual tree, sections
>   filtered to "Question Response Analysis", "Question Response Analysis by
>   Teacher", "Question Response Analysis by Standard and Teacher")
> - `data/_pbix_extract/20_pages.md:264-343`
> - `data/_pbix_extract/22_fields_per_page.json:426-624`
> - `data/_pbix_extract/04_dax_measures.dax` (verbatim measure bodies)
> - `data/_pbix_extract/03_schema.csv` (table/column inventory)
> - The three PDFs in `data/sample reports/`
> - Existing implementation: `data/_pbix_extract/51_qra_spec.md`,
>   `frontend/src/components/app/modules/reports/qra/*`,
>   `backend/app/repositories/cube_repository.py`,
>   `backend/app/services/report_service.py`
> - Per-page extract dumps in
>   `.planning/reports-expansion/qra-paginated-notes/ord11_qra.json`,
>   `ord12_qra_by_teacher.json`, `ord13_qra_by_std_teacher.json`
>
> **Companion**: `data/_pbix_extract/51_qra_spec.md` covers PBIX page #17
> (Interactive). That spec ↔ the rendered React page. This spec covers
> pages #11, #12, #13 (Paginated).

---

## §0. Shared chrome — identical across the three variants

All three paginated pages are `1280.0 × 720.0`, `displayOption: 1`
(actual size), `outspace.color = '#CACEDA'` (page background). The seven
chrome visuals on each page are byte-for-byte identical in **position**,
**size**, **field bindings**, and **formatting** — only their `name` GUIDs
differ. Reference coordinates below are read from
`.planning/reports-expansion/qra-paginated-notes/ord11_qra.json`; ord12 /
ord13 match to ≤0.01px.

| # | type | x, y, w, h (px) | z | role | binding / measure | notes |
|---|---|---|---|---|---|---|
| 1 | `actionButton` | 28.16, 15.54, 81.58, 73.81 | 6000 | Hyperlink (back / home) — `icon.show=false`, `outline.show=false`, `shape.roundEdge=0` | _none_ | Transparent overlay over the school logo, used as a navigation hotspot. |
| 2 | `simpleImageEBC4593F96F1425FB3D84C5BF02B5075` | 27.74, 17.46, 76.02, 71.91 | 5000 | logo | `SchoolLogo_Parameter.SchoolLogo_Parameter` (Column) | Custom-visual GUID = simple image visual; bound to the M parameter `SchoolLogo_Parameter`. |
| 3 | `multiRowCard` | 120.93, 10.96, 490.19, 40.28 | 7000 | "Paginated PDF Report \|" banner | `Titles.H1 - Longitudinal` | Theme color id 1 (primary); font 18pt; `card.barShow=false`, `cardPadding=20`. |
| 4 | `multiRowCard` | 528.55, 0.00, 533.89, 48.05 | 0 | KPI strip (5 cells) | `Key Measures.Total Questions`, `Key Measures.Total Students`, `Key Measures.Score`, `Sum(Student Submissions.Points Possible)`, `Key Measures.% of Correct Answers` | No formatting overrides. |
| 5 | `textbox` | 346.74, 17.25, 679.68, 37.09 | 3000 | empty (decorative spacer) | _none_ | `general.paragraphs[0].textRuns[0].value = ""`. |
| 6 | `multiRowCard` | 122.07, 58.18, 582.96, 39.93 | 1000 | "Course: <Grade>: <Item_Name>" | `Titles.H2 - Course and Unit` | Color: theme id 2 at −0.5 (darker tint); font 16pt; visual-level Advanced filter on `Titles.H2 - Course and Unit` hidden in view mode (`isHiddenInViewMode=true`). |
| 7 | `multiRowCard` | 122.07, 88.98, 499.68, 38.79 | 2000 | Assessment type label | `Titles.H2 - Assessment Type` | Same theme/filter pattern as #6, font 14pt. |
| 8 | `rdlVisual` | 11, 127, 1256, 577 | 4000 | **The embedded RDL report — body table** | varies per page (see §1–§3) | The full-width body. `autoFilter.show=true`. |

**Page background (all three):** `outspace.color = '#CACEDA'` (light lavender-grey).

**KPI multiRowCard (#4) — verbatim DAX dependencies**

`Key Measures.*` is a synonym table for measures stored on `Measure`. The
five cells map to:

```dax
-- 04_dax_measures.dax:148 (table: Measure)
MEASURE [Total Question] =
    DISTINCTCOUNT('cube_question_summary_overall'[Question_No])
```

```dax
-- 04_dax_measures.dax:134 (table: Measure)
MEASURE [Total Student] =
SUMX(
    SUMMARIZE(
        'cube_school_summary',
        'cube_school_summary'[Item_ID],
        "UniqueTotalQuestions", MAX('cube_school_summary'[Total_Students])
    ),
    [UniqueTotalQuestions]
)
```

```dax
-- 04_dax_measures.dax:482 (table: Measure)
MEASURE [Score] =
SUM('cube_questionincorrectchoice_summary'[Total_Score])
```

```dax
-- 04_dax_measures.dax:475 (table: Measure)
MEASURE [% Correct Answer] =
AVERAGE('cube_question_summary_overall'[Grade_Average])
```

(`Sum(Student Submissions.Points Possible)` is the raw column sum, no
measure indirection.)

**Header textbox / banner measures**

```dax
-- 04_dax_measures.dax:656 (table: Titles)
MEASURE [H1 - Longitudinal] =
"Paginated PDF Report |"
```

```dax
-- 04_dax_measures.dax:320 (table: Titles)
MEASURE [H2 - Assessment Type] =
VAR _fieldValue = VALUES(dim_subject[Assessment_type])
VAR _trimmedValues =
    SELECTCOLUMNS(
        _fieldValue,
        "TrimmedAssessment", TRIM(SUBSTITUTE(dim_subject[Assessment_type], "  ", " "))
    )
RETURN
CONCATENATEX(
    DISTINCT(_trimmedValues),
    [TrimmedAssessment],
    ", "
)
```

```dax
-- 04_dax_measures.dax:340 (table: Titles)
MEASURE [H2 - Course and Unit] =
var _Title = "Course: "
var _fieldValue = VALUES('dim_subject'[Grade])
var _fieldValue2 = VALUES('dim_item'[Item_Name])
var _field = MIN('dim_subject'[Grade])
Return
CONCATENATEX (
_fieldValue,
'dim_subject'[Grade],
", "
)&
": "&
CONCATENATEX (
_fieldValue2,
'dim_item'[Item_Name],
", "
)
```

```dax
-- 04_dax_measures.dax:279 (table: Titles)
MEASURE [Instructor(s):] =
 CONCATENATEX(
    DISTINCT('dim_Item'[Section_Instructors]),
    'dim_Item'[Section_Instructors],
    UNICHAR(10)
)
```

The `Titles.H3 - Teachers` reference in the layout JSON for ord 11
(see §1) targets the same `Instructor(s):` measure body (the "H3 -
Teachers" alias is the display name; `property` = `Instructor(s):`).

---

## §1. Question Response Analysis  (ord 11)

### Purpose
Per-item printable PDF — the canonical "give me one PDF per assessment
listing every question with the answer-key, % correct, the distractor
breakdown, and the **named list of students who chose each wrong
answer**." Audience: teachers and instructional coaches who want to walk
into a parent meeting with the page printed.

### Page geometry
`1280 × 720`, ord 11, 8 visuals, `displayOption=1`, background `#CACEDA`.

### Layout map (8 visuals)

| # | type | name (GUID) | position | binding |
|---|---|---|---|---|
| 1 | multiRowCard (KPI strip) | `83abd22ec670619db5d8` | (528.55, 0, 533.89, 48.05) | see §0 |
| 2 | multiRowCard (H1) | `ce168cb0e635c3668490` | (120.0, 11.97, 490.19, 40.28) | `Titles.H1 - Longitudinal` |
| 3 | actionButton | `f11261f72b60f929819f` | (28.16, 15.54, 81.58, 73.81) | _none_ |
| 4 | textbox (empty) | `46398c9e782bb65b87f2` | (346.74, 17.25, 679.68, 37.09) | _none_ |
| 5 | simpleImage (logo) | `a54c287507c4a2e3bd8a` | (27.74, 17.46, 76.02, 71.91) | `SchoolLogo_Parameter.SchoolLogo_Parameter` |
| 6 | multiRowCard (H2 Course and Unit) | `2ea889e59c45c61a9426` | (122.07, 58.18, 582.96, 39.93) | `Titles.H2 - Course and Unit` |
| 7 | multiRowCard (H2 Assessment type) | `be23e8301897a522f747` | (122.07, 88.98, 499.68, 38.79) | `Titles.H2 - Assessment Type` |
| 8 | **rdlVisual** | `b0faa2496104c879ca61` | (11, 127, 1256, 577) | _see below_ |

### rdlVisual field bindings (the parameters passed to the embedded RDL)

`_layout.full.json` → `ord 11` → visual `b0faa2496104c879ca61` →
`prototypeQuery.Select`:

| alias (queryRef) | kind | entity.property | native ref | RDL paramName |
|---|---|---|---|---|
| `dim_item.assessment_date` | Aggregation (`Last`, fn id 4 = `MAX`) | `dim_item.assessment_date` | `Last assessment_date` | `H3_AssessmentDate` |
| `dim_subject.Assessment_type` | Aggregation (`First`, fn id 3 = `MIN`) | `dim_subject.Assessment_type` | `First Assessment_type` | `AssessmentType` |
| `dim_subject.Grade` | Aggregation (`First`) | `dim_subject.Grade` | `First Grade` | `Grade` |
| `dim_subject.Subject` | Aggregation (`First`) | `dim_subject.Subject` | `First Subject` | `Subject` |
| `cube_question_summary_overall.Subject_ID` | Aggregation (`First`) | `cube_question_summary_overall.Subject_ID` | `First Subject_ID` | `cubequestionsummaryoverallSubjectID` *(multi-value)* |
| `Titles.H3 - Teachers` | Measure | `Titles.Instructor(s):` | `H3 - Teachers` | `H3_Teacher` |
| `dim_item.Item_Name` | Aggregation (`First`) | `dim_item.Item_Name` | `First Item_Name` | `Item_Name` |
| `SchoolLogo_Parameter.SchoolLogo_Parameter` | Column | `SchoolLogo_Parameter.SchoolLogo_Parameter` | `SchoolLogo_Parameter` | _not in mapping; consumed by the logo visual_ |

`reportId = 2019f225-26d9-478f-bf0f-9d6f67b45ecd`,
`workspaceId = 8215049c-ebd6-4a9b-bb98-5b5fdb7d3da4`.

`autoFilter.show = true` — Power BI is allowed to inject implicit
visual-level filters from page filters (which is how `Item_Name = 'Module
7 Test'` propagates from the page filter to the RDL parameters).

### Row grouping inside the RDL body (reconstructed from
`Paginated - Question Response Analysis.pdf`)

The RDL has **one tablix, no group rows, sorted ascending by
`% of Correct Answers`** (PDF page 1 starts at 52.8%, page 2 begins 60.4%
/ 64.2%, page 3 starts 69.8% / 71.7%, …). The whole assessment fits in
one report, paginated by row count (~3 questions per page given the row
height needed for the students-with-incorrect-choice column).

Detail row columns (left → right):

| Col | Header | Source | Aggregation |
|---|---|---|---|
| `No.` | `No` | `cube_question_summary_overall.Question_No` (or its `Sorting Question_No` equivalent) | First non-blank — `questionDax` style |
| `Question` | `Question` | `cube_question_summary_overall.Question` (HTML rendered as plain text) | `questionDax` (`FIRSTNONBLANK`) |
| `Standard` | `Standard` | `dim_question_data.standard` joined to `dim_standard.cpalms_standard` (display label, e.g. `R.1.1`, `V.1.2`) | first non-blank, no concat |
| `% of Correct Answers` | `% of Correct Answers` | `[% Correct Answer]` (`AVERAGE('cube_question_summary_overall'[Grade_Average])`) | Avg |
| `Correct Answer` | `Correct Answer` | `cube_question_summary_overall.Correct_Answer` | `__FirstFormatted_correct_` (Position_Number-prefixed multi-line) — see §0 / §5 |
| `Incorrect Choice details` | `Incorrect Choice details` | `cube_question_summary_overall.Incorrect_Choice_Details` | `__FirstFormatted_Incorrect_Choice_Details` (blank when grade_average == 1) |
| `Students with Incorrect Choice` | `Students with Incorrect Choice` | concat of `fact_student_submission.User_Name` per `Answer_Submission` for points_received≠1 | DAX `Incorrect Details Name` — see below |

**Subtotal rows:** none. Only one detail row band — no group totals.

**Header band style (from PDF):** header background `#D6F1EF` (light
cyan), header text dark grey, body cells white, percent cell tinted via
the standard traffic-light gradient (see §5).

#### DAX for the wrong-answer-students column (`Incorrect Details Name`)

```dax
-- 04_dax_measures.dax:517 (table: Measure)
MEASURE [Incorrect Details Name] =
VAR FilteredStudents =
    FILTER(
        'fact_student_submission',
        'fact_student_submission'[Points_Received] <> "1"
    )
VAR GroupedData =
    SUMMARIZE(
        FilteredStudents,
        'fact_student_submission'[Answer_Submission],
        "StudentNames", CONCATENATEX(
            FILTER(
                FilteredStudents,
                'fact_student_submission'[Answer_Submission] = EARLIER('fact_student_submission'[Answer_Submission])
            ),
            'fact_student_submission'[User_Name],
            ", "
        )
    )
RETURN
    CONCATENATEX(
        GroupedData,
        "[" & 'fact_student_submission'[Answer_Submission] & "]: " & UNICHAR(10) & "(" & [StudentNames] & ")",
        UNICHAR(10) & UNICHAR(10),
        'fact_student_submission'[Answer_Submission]
    )
```

This is the column that produces the long, vertically-stacked
`[c. She yawns and stretches.]:\n(Valentina Pis Corzo, Danea Dotson, …)`
text visible on page 1 of the PDF.

#### DAX for `Correct Answer` (Position_Number-prefixed)

```dax
-- 04_dax_measures.dax:726 (table: cube_question_summary_overall)
MEASURE [__FirstFormatted_correct_] =
VAR CombinedDetails =
    CONCATENATEX(
        FILTER(
            VALUES(cube_question_summary_overall[Position_Number]),
            NOT(ISBLANK(cube_question_summary_overall[Position_Number])) &&
            cube_question_summary_overall[Position_Number] <> "N/A" &&
            NOT(ISBLANK(FIRSTNONBLANK(cube_question_summary_overall[Correct_Answer], 1)))
        ),
        VAR CorrectAns = FIRSTNONBLANK(cube_question_summary_overall[Correct_Answer], 1)
        RETURN
            IF(
                ISBLANK(CorrectAns),
                "",
                cube_question_summary_overall[Position_Number] & ": " & CorrectAns
            ),
        UNICHAR(10),
        VALUE(cube_question_summary_overall[Position_Number]),
        ASC
    )
RETURN
    IF(
        ISBLANK(CombinedDetails),
        FIRSTNONBLANK(cube_question_summary_overall[Correct_Answer], 1),
        CombinedDetails
    )
```

#### DAX for `Incorrect Choice details`

```dax
-- 04_dax_measures.dax:778 (table: cube_question_summary_overall)
MEASURE [__FirstFormatted_Incorrect_Choice_Details] =
VAR GradeAverage = FIRSTNONBLANK(cube_question_summary_overall[Grade_Average], 1)
RETURN
    IF(
        GradeAverage = 1,
        BLANK(),
        VAR CombinedDetails =
            CONCATENATEX(
                FILTER(
                    VALUES(cube_question_summary_overall[Position_Number]),
                    NOT(ISBLANK(cube_question_summary_overall[Position_Number])) &&
                    cube_question_summary_overall[Position_Number] <> "N/A" &&
                    NOT(ISBLANK(FIRSTNONBLANK(cube_question_summary_overall[Incorrect_Choice_Details], 1)))
                ),
                VAR IncorrectDetail = FIRSTNONBLANK(cube_question_summary_overall[Incorrect_Choice_Details], 1)
                RETURN
                    IF(
                        ISBLANK(IncorrectDetail),
                        "",
                        cube_question_summary_overall[Position_Number] & ": " & IncorrectDetail
                    ),
                UNICHAR(10),
                VALUE(cube_question_summary_overall[Position_Number]),
                ASC
            )
        RETURN
            IF(
                ISBLANK(CombinedDetails),
                FIRSTNONBLANK(cube_question_summary_overall[Incorrect_Choice_Details], 1),
                CombinedDetails
            )
    )
```

### Filters / parameters

- **Page-level filter** (`_layout.full.json` → ord 11 → `filters`):
  Categorical filter on `dim_item.Item_Name`, in the sample PBIX hard-coded
  to `['Module 7 Test']` (`howCreated=5` = drill-through filter). When the
  Home page drills through to this paginated report, Power BI substitutes
  the clicked Item_Name into this filter slot.
- **Visual-level filters** on visuals 6 and 7 (the H2 multiRowCards):
  Advanced filter binding to the same measure (`Titles.H2 - Course and
  Unit` / `Titles.H2 - Assessment Type`), `isHiddenInViewMode=true`. These
  prevent the multiRowCard from rendering when its underlying value would
  be `BLANK()` (so the card cell collapses cleanly instead of showing an
  empty bar).
- **No `Drill Through Report` slicer** on the page — this is a pure
  paginated render target, not a navigation target.
- **No `dim_item.Item_ID` filter** — ord 11 keys on Item_Name (string),
  whereas ord 12 and ord 13 additionally key on `dim_item.Item_ID` (uuid)
  via the `cube_user_summary.Item_Name` shadow filter (see §2).

### Conditional formatting

The `% of Correct Answers` body cell shading visible in the PDF (pink for
52.8 / 60.4 / 64.2 / 69.8 %; yellow for 71.7 %; would-be green at
≥80 %) is **applied inside the RDL**, not by the PBIX-level
`Performance Color *` measures. The PBIX measures still exist
(`Performance Color Question` at `04_dax_measures.dax:576`, `Performance
Color Standard` at `:250`) — they're authored for the *interactive* page
and are reused by the RDL author as a reference, but the actual cell
fill in the RDL is set by an RDL `BackgroundColor` expression along the
same thresholds:

```
< 0.70   → #FFCCFF  (pink)
0.70-0.80 → #FFFF00 (yellow, RDL renders yellow rather than the PBIX `Yellow` named color)
>= 0.80  → #00FF06  (longitudinal green)
```

(Cross-referenced against the PBIX `Performance Color Standard` DAX
below.)

```dax
-- 04_dax_measures.dax:250 (table: Measure)
MEASURE [Performance Color Standard] =
VAR High = 0.8
VAR Low = 0.7
VAR Selectedattribute = AVERAGE('cube_question_summary_overall'[Grade_Average])
VAR Result =
        SWITCH(TRUE(),
        Selectedattribute>=High, "#00FF06", //longitudinal green
        AND(Selectedattribute<Low,Selectedattribute>=0), "#FFCCFF",
        ANd(Selectedattribute>=Low,Selectedattribute<High), "Yellow"
        )
Return Result
```

The **header cell background** is `#D6F1EF` (PBIX theme color 6 — light
cyan, the same swatch used as the table header in the interactive QRA
StrandsTable).

### PDF cross-check (`Paginated - Question Response Analysis.pdf`)

- **Title**: `Question Response Analysis` (top-left, bold, ~28pt).
- **Subhead row 1**: `Lesson  Assessments` (two spaces — matches the
  `[H2 - Assessment Type]` trimming behavior on the comma-separated
  source).
- **Subhead row 2**: `ELA - Grade 1: Tell Me a Story: Weekly Assessment:
  Week 2` (Course and Unit).
- **Right-aligned line**: `Assessment Date: 08/05/2026` (visible only on
  page 1 of the sample — driven by RDL `H3_AssessmentDate` parameter).
- **Below the heading bar** (left column, italic/regular): the list of
  Section Instructors, one per line — `Mason Reeder / Elizabeth Sedlak /
  Taylor Almendinger` — exactly what `Instructor(s):` produces.
- **Table columns** (7): `No`, `Question`, `Standard`, `% of Correct
  Answers`, `Correct Answer`, `Incorrect Choice details`, `Students with
  Incorrect Choice`. Header band light-cyan, header text bold dark
  grey.
- **Cell shading** in the `% Correct` column: pink, pink, pink, yellow on
  the four sample rows — matches the threshold table above.
- **Footer**: `Generated at 05/11/2026 14:30:32 UTC` (left), `Page N of M`
  (right). RDL standard page footer.

Sort order: ascending by `% of Correct Answers`. (Lowest-scoring question
first — this is the action-oriented teacher view: "where do my students
struggle most?")

---

## §2. Question Response Analysis by Teacher  (ord 12)

### Purpose
Same per-item PDF, **broken out by Section_Instructor**. The RDL inserts
a `Teacher: <name>` band header before each teacher's question list and
restarts the question table for every distinct instructor. Each
instructor's questions are still sorted ascending by % correct, but the
table is partitioned by teacher first. Audience: per-classroom postmortems
("How did *my* class do on each question vs. the school?").

The "Students with Incorrect Choice" column is **dropped** in this variant
— per-teacher question rows do not enumerate students. The RDL therefore
has 6 columns instead of 7 (compare PDF page 1: `No`, `Question`,
`% of Correct Answers`, `Correct Answer`, `Incorrect Choice details`
— wait, the PDF actually shows `Standard` missing too on the by-Teacher
page 1; see "PDF cross-check" below for the actual rendered set).

### Page geometry
`1280 × 720`, ord 12, 8 visuals, same shell as ord 11.

### Layout map (8 visuals)

| # | type | name (GUID) | position (same as ord 11) | binding |
|---|---|---|---|---|
| 1 | multiRowCard (KPI strip) | `d03d687d22589d7888d0` | (528.55, 0, 533.89, 48.05) | as §0 |
| 2 | multiRowCard (H1) | `8ff8d4a4387bcfbbe6f4` | (120.93, 10.96, 490.19, 40.28) | `Titles.H1 - Longitudinal` |
| 3 | actionButton | `e797e56e80fc57a188fe` | (28.16, 15.54, 81.58, 73.81) | _none_ |
| 4 | textbox (empty) | `dddc53f6f1cb328a8acb` | (346.74, 17.25, 679.68, 37.09) | _none_ |
| 5 | simpleImage (logo) | `961a3b74b06be43b2635` | (27.74, 17.46, 76.02, 71.91) | `SchoolLogo_Parameter.SchoolLogo_Parameter` |
| 6 | multiRowCard (H2 Course and Unit) | `ffb60d40ac5d89810b95` | (122.07, 58.18, 582.96, 39.93) | `Titles.H2 - Course and Unit` |
| 7 | multiRowCard (H2 Assessment type) | `6886a1400b54c4efbc20` | (122.07, 88.98, 499.68, 38.79) | `Titles.H2 - Assessment Type` |
| 8 | **rdlVisual** | `2be39a89865b001608b6` | (11, 127, 1256, 577) | _see below_ |

### rdlVisual field bindings

`_layout.full.json` → ord 12 → visual `2be39a89865b001608b6` →
`prototypeQuery.Select`:

| alias (queryRef) | kind | entity.property | native ref | RDL paramName |
|---|---|---|---|---|
| `dim_item.Item_ID` | Column | `dim_item.Item_ID` | `Item_ID` | `cubequestionsummaryItemID` (multi-value) |
| `dim_item.Item_Name` | Column | `dim_item.Item_Name` | `Item_Name` | `cubequestionsummaryItemName` (multi-value) |
| `dim_subject.Grade` | Column | `dim_subject.Grade` | `Grade` | `cubequestionsummaryGrade` (multi-value) |
| `dim_subject.Subject` | Column | `dim_subject.Subject` | `Subject` | `cubequestionsummarySubject` (multi-value) |
| `dim_subject.Assessment_type` | Column | `dim_subject.Assessment_type` | `Assessment_type` | `cubequestionsummaryAssessmenttype` (multi-value) |
| `dim_subject.Session` | Column | `dim_subject.Session` | `Session` | `cubequestionsummarySession` (multi-value) |

`reportId = 43a35555-38c4-4b20-85e7-1f9784889cad`,
`workspaceId = 8215049c-ebd6-4a9b-bb98-5b5fdb7d3da4`.

Difference vs. ord 11:
- **Six raw columns** (no Aggregation wrappers, no `First`/`Last`).
- **No `Subject_ID` parameter** — the RDL keys on `Item_ID` directly.
- **No `H3_Teacher` parameter** — the RDL fans out by `Section_Instructors`
  on its own side (the teacher list is read from
  `cube_question_summary.Section_Instructors` /
  `cube_question_summary_overall.Section_Instructors`,
  `migrations/20260507000070_cube_tables.sql:95,142`).
- **No `SchoolLogo_Parameter` selection** — the RDL renders without the
  per-tenant logo (the PBIX shell #5 still shows the logo).

### Row grouping inside the RDL body
(reconstructed from `Paginated - Question Response Analysis By  Teacher.pdf`)

Tablix grouping hierarchy:

```
Group 1:  Section_Instructors  (page-break before each new value)
  Detail: Question_No  (sorted asc by % Correct)
```

- **Group 1 band**: A bold left-aligned `Teacher: <Instructor Name>` row
  printed just under the Course/Unit header. Each group starts a **new
  page** (`PageBreak.BreakLocation = Start` on the group). PDF page 1 is
  `Teacher: Taylor Almendinger`; PDF page 11 is `Teacher: Mason Reeder`.
- **Detail rows** identical to ord 11 *except*:
  - **`Students with Incorrect Choice` column is absent**.
  - **`Standard` column is absent** (visible in PDF page 1 of by-Teacher:
    columns are `No`, `Question`, `% of Correct Answers`, `Correct
    Answer`, `Incorrect Choice details`). NB: a "Standard" column header
    is visible on certain intermediate / orphan pages (e.g. PDF page 2 and
    page 10), which appears to be a rendering artefact where the tablix
    page-break leaves a continuation header band stranded; this is an
    RDL-layout quirk to **preserve, not fix** when rebuilding for
    legacy-mirror parity.
- **No subtotal row** per teacher in the rendered PDF. (Contrast with §3.)

### Field bindings (detail row, reconstructed)

| Col | Header | Source |
|---|---|---|
| `No.` | `No` | `cube_question_summary.Question_No` |
| `Question` | `Question` | `cube_question_summary.Question` (the per-section grain, since this report is per-teacher) |
| `% of Correct Answers` | `% of Correct Answers` | `AVERAGE(cube_question_summary[Grade_Average])` filtered to the current teacher's `Section_Instructors` |
| `Correct Answer` | `Correct Answer` | `cube_question_summary.Correct_Answer`, Position_Number-prefixed (same `__FirstFormatted_correct_` logic as §1, but the source table is `cube_question_summary`, not `cube_question_summary_overall`) |
| `Incorrect Choice details` | `Incorrect Choice details` | `cube_question_summary.Incorrect_Choice_Details`, percent-prefixed |
| _(implicit group header)_ | `Teacher: <name>` | `cube_question_summary.Section_Instructors` |

### Filters / parameters

- **Page-level filter 1**: Categorical on
  `cube_user_summary.Item_Name`. **`cube_user_summary` is not in the
  loaded model** (it's not in `02_tables.json`); this is a *shadow filter*
  carried over from an earlier composite-model state. Power BI tolerates
  it as long as the entity is empty / unreferenced at runtime — it
  manifests as a no-op page filter slot. Treat it as **legacy ballast**;
  do not re-create it in our rebuild unless we re-introduce the
  composite-model topology.
- **Page-level filter 2**: Categorical on `dim_item.Item_Name`, hard-coded
  to `['Module 7 Test']`, `howCreated=5` (drill-through). Same role as
  the ord-11 page filter — drives the per-Item parameterization.
- **Visual-level filters** on H2 multiRowCards (#6, #7): same Advanced
  filter on the H2 measures as §0.

### Conditional formatting

Same thresholds as ord 11 (`<0.70 → #FFCCFF`, `0.70–0.80 → #FFFF00`,
`≥0.80 → #00FF06`). Cell shading on `% of Correct Answers` only.

Bold-weight on every cell of the per-teacher group header band; regular
weight on detail rows.

### PDF cross-check (`Paginated - Question Response Analysis By  Teacher.pdf`)

- **Title**: `Question Response Analysis`
- **Subtitle (italic)**: `By Classroom Instructor`
- **Subhead row 1**: `Lesson  Assessments` (assessment type)
- **Subhead row 2**: `ELA - Grade 1: Tell Me a Story: Weekly Assessment:
  Week 2`
- **Teacher band**: `Teacher: Taylor Almendinger` (bold, slightly larger
  text, left-aligned)
- **Columns** (5 visible on rendered page 1): `No`, `Question`,
  `% of Correct Answers`, `Correct Answer`, `Incorrect Choice details`
- **Sort**: ascending by `% of Correct Answers` (44.4% → 61.1% → 72.2% →
  72.2% on PDF page 1).
- **Multiple-instructor PDF**: 30 pages total. Page 11 starts
  `Teacher: Mason Reeder`. Page 2 / page 10 / page 20 show a stand-alone
  `Standard` column with a few code values (`R.1.1`, `V.1.2`, `R.1.1`,
  `F.1.4.a` / `R.1.1`, `R.3.1`, `F.1.3.c`, `F.1.3.c`) and **no other
  columns** — this is the RDL "tablix page-break continuation header"
  artefact noted above.
- **Footer**: `Generated at 05/11/2026 14:44:43 UTC` (left), `Page N of M`
  (right).

---

## §3. Question Response Analysis by Standard and Teacher  (ord 13)

### Purpose
Same per-item PDF, but **double-grouped: Standard, then Section
Instructor**. Each standard gets its own band with the question rows
inside it broken down per teacher, and each standard's band ends with a
**`Standard Average:`** subtotal row. Audience: alignment / RtI use cases
("On standard R.1.1 — which teacher is highest? Which is lowest? What's
the cohort average?").

### Page geometry
`1280 × 720`, ord 13, 8 visuals, same shell as ord 11.

### Layout map (8 visuals)

| # | type | name (GUID) | position | binding |
|---|---|---|---|---|
| 1 | multiRowCard (KPI strip) | `b8037c56b80e87dbd87e` | (528.55, 0, 533.89, 48.05) | as §0 |
| 2 | multiRowCard (H1) | `4a547fbfe3512c6743f3` | (120.93, 10.96, 490.19, 40.28) | `Titles.H1 - Longitudinal` |
| 3 | actionButton | `e48dd0a52cfcdf718b20` | (28.16, 15.54, 81.58, 73.81) | _none_ |
| 4 | textbox (empty) | `2ede279dc0e0af2c8257` | (346.74, 17.25, 679.68, 37.09) | _none_ |
| 5 | simpleImage (logo) | `7ede530287ee4452767e` | (27.74, 17.46, 76.02, 71.91) | `SchoolLogo_Parameter.SchoolLogo_Parameter` |
| 6 | multiRowCard (H2 Course and Unit) | `e5ea13d59a69d4846e5b` | (122.07, 58.18, 582.96, 39.93) | `Titles.H2 - Course and Unit` |
| 7 | multiRowCard (H2 Assessment type) | `94cf6be5de40f96c4cdc` | (122.07, 88.98, 499.68, 38.79) | `Titles.H2 - Assessment Type` |
| 8 | **rdlVisual** | `059957977702b13edd39` | (11, 127, 1256, 577) | _see below_ |

### rdlVisual field bindings

**Identical to ord 12.** Six raw columns from `dim_item` and `dim_subject`:

| alias | kind | entity.property | RDL paramName |
|---|---|---|---|
| `dim_item.Item_ID` | Column | `dim_item.Item_ID` | `cubequestionsummaryItemID` |
| `dim_item.Item_Name` | Column | `dim_item.Item_Name` | `cubequestionsummaryItemName` |
| `dim_subject.Grade` | Column | `dim_subject.Grade` | `cubequestionsummaryGrade` |
| `dim_subject.Subject` | Column | `dim_subject.Subject` | `cubequestionsummarySubject` |
| `dim_subject.Assessment_type` | Column | `dim_subject.Assessment_type` | `cubequestionsummaryAssessmenttype` |
| `dim_subject.Session` | Column | `dim_subject.Session` | `cubequestionsummarySession` |

`reportId = 0ffc8105-9687-4175-b14a-599466c1627e`,
`workspaceId = 8215049c-ebd6-4a9b-bb98-5b5fdb7d3da4`.

### Row grouping inside the RDL body
(reconstructed from `Paginated - Question Response Analysis By Standard And Teacher.pdf`)

Tablix grouping hierarchy:

```
Group 1:  Standard           (page-break before each new value; sorted asc by Standard code)
  Header row:  <Standard code>                               -- e.g. "ELA.1.C.3.1"
  Group 2:  Section_Instructor                                -- "Section Instructor: <name>"
    Header row:  <bold Section Instructor: name> | <% Avg>
    Detail:  Question_No   (sorted asc by Question_No)
  Footer row (Group 1): "Standard Average:" | <standard-level % Avg>
```

- **Group 1 header** is the bare standard code, rendered in the
  page-content body area (NOT inside the tablix header band) — see PDF
  page 1: `ELA.1.C.3.1` printed above the tablix; page 2: `ELA.1.F.1.3`;
  page 3 contains two standards on the same page (`ELA.1.F.1.4` and
  `ELA.1.R.1.1`), confirming that a "Standard" group doesn't *always*
  force a page-break — it page-breaks **when the next standard would not
  fit** (`PageBreak.BreakLocation = StartAndEnd, ResetPageNumber = false,
  Disabled = =Iif(<remaining-space-fits-next>, True, False)`).
- **Group 2 header** is `Section Instructor: <name>` (bold) in the
  `Question` column, with the cohort-level average percent shown in the
  `% of Correct Answers` column for that teacher × standard pair (the
  yellow/green/pink cell tint applies to this header too — see PDF page 1
  where each section header `84.4% / 84.2% / 88.9%` is rendered in the
  same green band as the detail rows).
- **Detail rows** identical to ord 12 (no Students column, no Standard
  column since Standard is now the outer group).
- **Group 1 footer**: a `Standard Average:` row in italics with the
  standard-level cohort percent (page 1: 85.8% green; page 2: 99.1% green;
  page 3 `ELA.1.F.1.4`: 90.2% green; page 3 `ELA.1.R.1.1`: row absent
  because that standard continues on a later page).

### Field bindings (detail row + group rows, reconstructed)

| Row band | Col | Header | Source | Aggregation |
|---|---|---|---|---|
| Group 1 header | full row | `<Standard code>` | `dim_question_data.standard` / `dim_standard.cpalms_standard` | first-non-blank in scope |
| Group 2 header | `Question` | `Section Instructor: <name>` | `cube_question_summary.Section_Instructors` | string literal + first-non-blank |
| Group 2 header | `% of Correct Answers` | `XX.X%` | `AVERAGE(cube_question_summary[Grade_Average])` filtered to (current standard × current teacher) | Avg |
| Detail | `No` | `Question_No` | `cube_question_summary.Question_No` | _none_ |
| Detail | `Question` | `Question` | `cube_question_summary.Question` | first-non-blank |
| Detail | `% of Correct Answers` | `XX.X%` | `AVERAGE(cube_question_summary[Grade_Average])` filtered to (current standard × current teacher × current question) | Avg |
| Detail | `Correct Answer` | `Correct Answer` | `cube_question_summary.Correct_Answer` | `__FirstFormatted_correct_` style |
| Detail | `Incorrect Choice details` | `Incorrect Choice details` | `cube_question_summary.Incorrect_Choice_Details` | `__FirstFormatted_Incorrect_Choice_Details` style |
| Group 1 footer | `Question` | `Standard Average:` (italic, right-aligned) | string literal | — |
| Group 1 footer | `% of Correct Answers` | `XX.X%` | `AVERAGE(cube_question_summary[Grade_Average])` filtered to current standard only | Avg |

### Filters / parameters

- Same two page-level filters as ord 12 (`cube_user_summary.Item_Name` as
  legacy ballast; `dim_item.Item_Name = 'Module 7 Test'` drill-through).
- Same visual-level Advanced filters on the two H2 multiRowCards.

### Conditional formatting

Same thresholds (`<0.70 → #FFCCFF`, `0.70–0.80 → #FFFF00`, `≥0.80 →
#00FF06`). Applied to:
- The Group 2 (teacher) header `% of Correct Answers` cell (e.g. 84.4%
  → green, 84.2% → green, 88.9% → green on PDF page 1).
- Every detail-row `% of Correct Answers` cell.
- The Group 1 footer `Standard Average:` cell.

Bold weight on the Group 2 header row. Italic on the Group 1 footer
`Standard Average:` label.

### PDF cross-check (`Paginated - Question Response Analysis By Standard And Teacher.pdf`)

- **Title**: `Question Response Analysis`
- **Subtitle (italic)**: `By Standard and by Classroom Instructor`
- **Subhead row 1**: `Lesson  Assessments`
- **Subhead row 2**: `ELA - Grade 1: Tell Me a Story: Weekly Assessment:
  Week 2`
- **Group 1 header**: bare standard code, e.g. `ELA.1.C.3.1`,
  `ELA.1.F.1.3`, `ELA.1.F.1.4`, `ELA.1.R.1.1`. (PDF page 1 standard
  prefix is `ELA.1.C.3.1` — note this is the CPALMS-style display, not
  the Schoology short form `R.1.1`. The standard label source resolves
  through `dim_standard.cpalms_standard` not
  `dim_standard.schoology_short_standard`.)
- **Columns** (5): `No`, `Question`, `% of Correct Answers`, `Correct
  Answer`, `Incorrect Choice details` (same set as ord 12).
- **Group 2 header**: `Section Instructor: Elizabeth Sedlak`, `Section
  Instructor: Mason Reeder`, `Section Instructor: Taylor Almendinger`
  — three instructors per standard, alphabetical.
- **Group 1 footer**: `Standard Average:` row with the cohort average
  percent.
- **Sort within a teacher**: ascending by `Question_No` (PDF page 1
  shows Q12 then Q11 — actually descending; check: ELA.1.C.3.1 page
  shows `12, 11, 12, 11, 12, 11` across the three teachers — so it's
  sorted asc by `% of Correct Answers` *within teacher* (75.0% < 93.8%,
  78.9% < 89.5%, 83.3% < 94.4%). Confirmed: same intra-group sort as ord
  11 / 12 — ascending by % Correct.
- **Footer**: `Generated at 05/11/2026 14:52:58 UTC` (left), `Page N of
  M` (right). 14 pages total in the sample.

---

## §4. Comparison vs. the Interactive QRA

### Overlap with the existing implementation (`51_qra_spec.md` §2 + frontend `qra/`)

**Same data source:** all three paginated variants ultimately query
`cube_question_summary` and/or `cube_question_summary_overall`, scoped by
`item_id` (via Item_Name+Item_ID page filter) — **the same two tables the
interactive page already reads** through `CubeRepository.get_questions_
overall_for_item` (`backend/app/repositories/cube_repository.py:278`) and
`CubeRepository.get_question_overall`
(`backend/app/repositories/cube_repository.py:1612`).

**Same KPI strip math:** the `multiRowCard` "Total Questions / Total
Students / Score / Points Possible / % Correct" maps exactly to the
canonical KPI helper at `cube_repository.py:104+` which
`build_question_response_analysis`
(`backend/app/services/report_service.py:413`) already calls. The
paginated KPI strip is just the same five values rendered as a horizontal
multiRowCard at top-right instead of the 6-card grid the React page
draws. **No new KPI math required.**

**Same DAX measures (verbatim) in §0/§1:**

| Measure | Verbatim DAX in this doc | Already implemented as |
|---|---|---|
| `Total Question` | §0 | `KPIs.total_questions` via canonical CTE (`cube_repository.py:170-180`) |
| `Total Student` | §0 | `KPIs.total_students` (`cube_school_summary.total_students` max-by-item) |
| `Score` | §0 | `KPIs.total_score` (sum over `cube_questionincorrectchoice_summary.total_score`) |
| `% Correct Answer` | §0 | `KPIs.grade_average` (canonical per-(user,question)) |
| `Instructor(s):` | §0 | `KPIs.instructors[]` (`report_service.py:473`) |
| `__FirstFormatted_correct_` | §1 | `question.correct_answer` joined with `question.position_number` — payload carries both; the React `QuestionDetailTable.tsx:107` joins them but on `,` not on `\n` (a known minor parity gap, see `51_qra_spec.md` §7 item 3). |
| `__FirstFormatted_Incorrect_Choice_Details` | §1 | `question.incorrect_choice_details` — already carries the percent-of-cohort-prefixed string (`X.XX% chose [Y]`). |
| `Incorrect Details Name` | §1 | `report_service.py` already exposes `incorrect_choices[]` for the Incorrect Answer Details popover; **not yet wired into the QRA payload's per-question row** — only `incorrect_details_name` (raw string) is carried. |
| `Performance Color Standard` | §1/§2/§3 | `frontend/src/lib/reports/colors.ts` `cellColor()` — same thresholds 0.7 / 0.8. **The pink-vs-transparent divergence noted in `51_qra_spec.md` §3 applies here too** — paginated PDFs strictly use `#FFCCFF` pink, our React cellColor returns `transparent` under 0.7. The paginated rebuild MUST use real `#FFCCFF` to match the PDF. |
| `H1 - Longitudinal` | §0 | hard-coded string `"Paginated PDF Report \|"` — backend can return it as a constant. |
| `H2 - Assessment Type`, `H2 - Course and Unit` | §0 | already in `AssessmentMeta` (assessment_type, grade, item_name) — frontend just needs the format string. |

### What is NEW for the paginated variants (and not yet in the React `qra/`)

For **all three** paginated PDFs:

1. **Per-teacher question grain** — `cube_question_summary` carries
   `section_instructors` per row (`migrations/20260507000070_cube_tables.sql:95`),
   and so does `cube_question_summary_overall` (`:142`), but
   `get_questions_overall_for_item` aggregates *across all sections*
   (it has no `section_instructors` grouping). ord 12 and ord 13 both
   need a per-(question, section_instructor) read.

2. **`Students with Incorrect Choice` column** (ord 11 only) — the
   row-level concat of student names per incorrect answer submission.
   `report_service.py` already calls
   `cube.get_incorrect_choices_for_item(item_id)` (returns the
   `cube_questionincorrectchoice_summary` distractor breakdown) but
   **without the per-distractor student-name lists**. The DAX
   `Incorrect Details Name` (§1) reads `fact_student_submission`
   directly and groups student names by (question, answer_submission)
   where `points_received <> "1"`. That's a new fact-table query.

3. **`Standard Average:` subtotal** (ord 13 only) — per-standard
   cohort average across all teachers. This is `AVG(grade_average)` over
   `cube_question_summary` grouped by `(item_id, standard)`.

4. **Per-(teacher × standard) average** (ord 13 only) — used in the
   Group 2 header cell. `AVG(grade_average)` over `cube_question_summary`
   grouped by `(item_id, standard, section_instructors)`.

5. **Ascending sort by `% Correct`** — the interactive page leaves
   question rows in their natural (`question_no`) order. The paginated
   PDFs sort ascending by `% Correct` to highlight problem questions
   first.

6. **CPALMS-style standard label** on ord 13 group header (e.g.
   `ELA.1.C.3.1`) — not `R.1.1` Schoology short form. Source is
   `dim_standard.cpalms_standard`; the current
   `get_questions_overall_for_item` returns the Schoology code via
   `qd_standards` (newline-joined). Ord 13's grouping needs the CPALMS
   identifier as the GROUP BY key.

### Reuse-or-new repository call

For each new repository call below, give the SQL shape, not the SQL:

| Variant | New repo method | Query shape | Reuses |
|---|---|---|---|
| ord 11 | `get_incorrect_choice_students_for_item(item_id) -> List[(question_id, answer_submission, [student_names])]` | `SELECT question_id, answer_submission, ARRAY_AGG(user_name ORDER BY user_name) FROM fact_student_submission WHERE item_id = :item_id AND points_received <> '1' GROUP BY question_id, answer_submission ORDER BY question_id, answer_submission`. Join into the existing `questions_overall` rows by `question_id`. | `get_questions_overall_for_item` (rest of the row) |
| ord 12 | `get_questions_by_teacher_for_item(item_id) -> List[(section_instructor, question_id, question_no, question, correct_answer, grade_average, incorrect_choice_details, position_number)]` | Mirror `get_questions_overall_for_item` but **group by `section_instructors` first**, reading from `cube_question_summary` directly (not joining qso, since the per-section grain is in qs). Sort `ORDER BY section_instructors, grade_average ASC, question_no`. | Same DAX semantics as ord 11; the `__FirstFormatted_*` logic re-runs against the per-section row's `position_number` / `correct_answer`. |
| ord 13 | `get_questions_by_standard_teacher_for_item(item_id) -> List[(cpalms_standard, section_instructor, question_id, question_no, %correct, correct_answer, incorrect_choice_details), plus standard_avg, plus teacher_in_standard_avg]` | Three nested aggregations: (a) detail rows: `SELECT cpalms_standard, section_instructors, question_id, …` joining `cube_question_summary` × `dim_question_data` × `dim_standard`; (b) `WINDOW AVG(grade_average) OVER (PARTITION BY item_id, cpalms_standard, section_instructors)` for the Group-2 header; (c) `WINDOW AVG(grade_average) OVER (PARTITION BY item_id, cpalms_standard)` for the Group-1 footer. ORDER BY `cpalms_standard, section_instructors, grade_average ASC`. | `get_questions_overall_for_item`'s join machinery; `dim_question_data.standard → dim_standard.cpalms_standard` lookup (the seed already has both columns — see `docs/audit/legacy-schoology-cpalms-mapping.md`). |

**Recommendation:** none of the existing methods can be reused
unchanged. The shape we need is *per-(section × question)* or
*per-(standard × section × question)*, with optional grouping
aggregates. The existing methods aggregate across sections via DISTINCT
ON. **Three new repository methods** as above are the minimum delta.

Each variant should be served by its own service entry point
(`build_question_response_analysis_paginated`,
`build_question_response_analysis_by_teacher`,
`build_question_response_analysis_by_standard_and_teacher`) — the
schemas are different enough (Group-2 header rows, Standard footer)
that a single endpoint with a `variant` flag would force the frontend
into casting unions.

---

## §5. Shared base & deltas across the three paginated variants

### Shared base (identical across ord 11 / 12 / 13)

- **Page geometry**: 1280 × 720, `displayOption=1`, `outspace.color =
  '#CACEDA'`.
- **Page header chrome (7 visuals, positions byte-identical)**:
  H1 multiRowCard + KPI multiRowCard (5 cells) + actionButton + textbox
  + simpleImage logo + H2-Course-and-Unit multiRowCard + H2-Assessment-
  Type multiRowCard.
- **Page-level Item_Name drill-through filter**: `dim_item.Item_Name ∈
  ['Module 7 Test']`, `howCreated=5`.
- **Body** = a single full-width `rdlVisual` at `(11, 127, 1256, 577)`,
  z=4000, `autoFilter.show=true`.
- **Body-table column set (subset/superset relation)**:
  - Always present: `No`, `Question`, `% of Correct Answers`, `Correct
    Answer`, `Incorrect Choice details`.
  - Ord 11 only: adds `Standard`, adds `Students with Incorrect Choice`.
- **Conditional formatting (color rules)**: identical traffic-light on
  `% of Correct Answers` — `<0.70 → #FFCCFF`, `0.70–0.80 → #FFFF00`,
  `≥0.80 → #00FF06`.
- **Header band style**: light cyan `#D6F1EF`, dark grey bold text.
- **Footer**: `Generated at <ts UTC>` (left), `Page N of M` (right).
- **Sort default**: ascending by `% of Correct Answers` (within the
  innermost group).
- **DAX measures consumed** (verbatim bodies cited in §0/§1): `Total
  Question`, `Total Student`, `Score`, `% Correct Answer`, `Instructor(s):`,
  `H1 - Longitudinal`, `H2 - Assessment Type`, `H2 - Course and Unit`,
  `__FirstFormatted_correct_`, `__FirstFormatted_Incorrect_Choice_
  Details`, `Performance Color Standard`. Ord 11 additionally uses
  `Incorrect Details Name`.

### Delta matrix

| Aspect | ord 11 (base) | ord 12 (by Teacher) | ord 13 (by Standard and Teacher) |
|---|---|---|---|
| Subtitle (italic) under `Question Response Analysis` | none | `By Classroom Instructor` | `By Standard and by Classroom Instructor` |
| RDL `reportId` | `2019f225-26d9-478f-bf0f-9d6f67b45ecd` | `43a35555-38c4-4b20-85e7-1f9784889cad` | `0ffc8105-9687-4175-b14a-599466c1627e` |
| RDL parameter set | 7 params: `cubequestionsummaryoverallSubjectID`, `Subject`, `Grade`, `H3_Teacher`, `AssessmentType`, `Item_Name`, `H3_AssessmentDate` | 6 params: `cubequestionsummaryItemID`, `cubequestionsummaryItemName`, `cubequestionsummaryGrade`, `cubequestionsummarySubject`, `cubequestionsummaryAssessmenttype`, `cubequestionsummarySession` | Same 6 params as ord 12 |
| Row source table | `cube_question_summary_overall` (per-school grain, aggregated across sections) | `cube_question_summary` (per-section grain) | `cube_question_summary` (per-section grain) |
| Tablix grouping | none (flat list of questions) | 1-level: `Section_Instructors` | 2-level: `Standard → Section_Instructors` |
| Per-group page-break | n/a | `Start` on Teacher | `Start` on Standard; Teacher is in-page |
| Group-header content | n/a | `Teacher: <name>` (bold) | Standard code (above tablix); `Section Instructor: <name>` (bold inside tablix, with its row's % shown) |
| Subtotal row | none | none | `Standard Average:` at the end of each Standard group |
| Columns in detail row | 7 (`No`, `Question`, `Standard`, `% Correct`, `Correct Answer`, `Incorrect Choice details`, `Students with Incorrect Choice`) | 5 (`No`, `Question`, `% Correct`, `Correct Answer`, `Incorrect Choice details`) | 5 (same as ord 12) |
| Extra page-level filter | `dim_item.Item_Name` only | `dim_item.Item_Name` **plus** `cube_user_summary.Item_Name` (shadow / legacy ballast) | `dim_item.Item_Name` **plus** `cube_user_summary.Item_Name` (shadow / legacy ballast) |
| Standard label source | n/a (Schoology short form `R.1.1`-style, comes through `cube_question_summary.standard`) | n/a | **CPALMS form** `ELA.1.C.3.1` — sourced from `dim_standard.cpalms_standard` not `schoology_short_standard` |
| Sample PDF page count (Module 7 Test, Tell Me a Story) | 8 pages | 30 pages | 14 pages |
| Intended audience | Cohort-wide assessment debrief; share with parents | Per-classroom instructor postmortem | Standards alignment / RtI |
| Likely render mode in our rebuild | One PDF/page download per assessment | One PDF/page download, sub-grouped client-side | One PDF/page download, sub-grouped client-side |

### Cross-variant data-wire summary

To rebuild all three from a single FastAPI endpoint family, the minimum
new payload fields are:

```
ord 11 payload additions (over the existing QRA payload):
  question.incorrect_students: List[{
    answer_submission: str,
    students: List[str]
  }]
  question.standard_display: str          # dim_standard.cpalms_standard
                                          # OR dim_question_data.standard
                                          # — the short-form already in payload
                                          # is fine, this only renames it for clarity

ord 12 payload (entirely new endpoint):
  teacher_groups: List[{
    section_instructor: str,
    questions: List[QuestionRow]          # same QuestionRow shape minus
                                          # incorrect_students / standards
                                          # — sorted asc by grade_average
  }]
  kpis: KPIs                              # same KPIs as ord 11
  assessment: AssessmentMeta              # same

ord 13 payload (entirely new endpoint):
  standard_groups: List[{
    cpalms_standard: str,
    standard_average: float,
    teacher_groups: List[{
      section_instructor: str,
      teacher_standard_average: float,    # AVG(grade_average) for this teacher × standard
      questions: List[QuestionRow]        # same QuestionRow shape minus
                                          # incorrect_students / standards
                                          # — sorted asc by grade_average
    }]
  }]
  kpis: KPIs                              # same KPIs
  assessment: AssessmentMeta              # same
```

### Notes on the legacy `cube_user_summary` shadow filter

`cube_user_summary` is referenced as an `Entity` in the page-level
filters of ord 12 and ord 13 (see `_layout.full.json` lines 1186 and
1280), and also in `cube_users_summary` form on the "Question Response
Analysis redacted" page (ord 18). **Neither table is in the loaded model
(`02_tables.json`)** — they are leftover composite-model references that
PBIX preserves syntactically but Power BI silently ignores at runtime
because the entity has no `From` source. Treat as **legacy ballast** for
rebuild purposes: do **not** introduce a `cube_user_summary` table to
satisfy this filter; the runtime behavior is identical to the
`dim_item.Item_Name` filter alone (which is also present in the same
filter array).

(If we ever revive a `cube_user_summary` table, it would be the
per-(user, item) roll-up; today it doesn't exist in
`backend/app/repositories/cube_repository.py` or
`supabase/migrations/`.)

### Notes on the embedded RDL bodies

The three `rdlVisual` references are by `reportId / workspaceId` — the
actual RDL `.rdl` XML files are **hosted on the Power BI service**, not
embedded in the PBIX. The reverse-engineering above is therefore based
on:

1. The PBIX-side parameter mappings (definitive: which fields flow into
   which RDL parameter).
2. The rendered PDFs (definitive for column ordering, group structure,
   sort order, conditional-formatting thresholds, header band style).
3. Matching DAX measures inside the PBIX model (used as the
   source-of-truth for the *formulas* the RDL author would have ported
   into RDL `Value` expressions — Power BI service RDL reports can call
   DAX-equivalent expressions via DataSet queries, and the body-table
   patterns in the PDF align with the DAX listed in §0/§1).

If the RDL `.rdl` XML is ever recovered (e.g. via Power BI service
export, or from `data/_pbix_unpacked/Report/ReportPackages/`), it
should be referenced here for any disputed cell expressions —
particularly the "Standard" column in ord 11 and the `Standard Average:`
footer formula in ord 13.

---

## §6. Implementation TL;DR for the rebuild team

For the team rebuilding these three reports as native (non-RDL,
non-Power-BI) endpoints in our stack:

1. **Reuse `AssessmentMeta` and `KPIs`** — both already exist on the
   QRA payload (`backend/app/schemas/reports.py`); same numbers as the
   PBIX KPI strip.
2. **Reuse `cellColor()` thresholds** but switch under-0.7 from
   `transparent` to `#FFCCFF` for the paginated rebuilds — the PDF
   shows pink. (Either lift the threshold map to a function param or
   add a sibling `paginatedCellColor()`.)
3. **Build 3 new FastAPI endpoints** under `/api/v1/reports/`:
   - `question-response-analysis-paginated/{item_id}` — ord 11; payload
     = QRA payload + `incorrect_students` per question.
   - `question-response-analysis-by-teacher/{item_id}` — ord 12; payload
     = grouped by `section_instructors`.
   - `question-response-analysis-by-standard-and-teacher/{item_id}` —
     ord 13; payload = grouped by `(cpalms_standard, section_
     instructors)` with subtotals.
4. **Three new repo methods** (shapes in §4 table).
5. **PDF output**: paginated reports are intended for print. Either
   render server-side via Playwright (current ecosystem fit) or
   client-side via `@react-pdf/renderer`. The body is plain HTML tables
   — no chart components needed.
6. **Sort intra-group ascending by `grade_average`** — matches PDF.
7. **Standard label format** — ord 11 uses Schoology short form (`R.1.1`)
   from `dim_question_data.standard`; ord 13 uses CPALMS long form
   (`ELA.1.C.3.1`) from `dim_standard.cpalms_standard`. Don't confuse the
   two. See `docs/audit/legacy-schoology-cpalms-mapping.md` for the
   alias relationship.

---

## Appendix A — Visual GUID cross-reference

For quick lookup against `_layout.full.json`:

```
ord 11 (Question Response Analysis):
  KPI strip          83abd22ec670619db5d8
  H1 banner          ce168cb0e635c3668490
  actionButton       f11261f72b60f929819f
  textbox            46398c9e782bb65b87f2
  logo               a54c287507c4a2e3bd8a
  H2 Course/Unit     2ea889e59c45c61a9426
  H2 Assess Type     be23e8301897a522f747
  rdlVisual          b0faa2496104c879ca61
                     reportId = 2019f225-26d9-478f-bf0f-9d6f67b45ecd

ord 12 (Question Response Analysis by Teacher):
  KPI strip          d03d687d22589d7888d0
  H1 banner          8ff8d4a4387bcfbbe6f4
  actionButton       e797e56e80fc57a188fe
  textbox            dddc53f6f1cb328a8acb
  logo               961a3b74b06be43b2635
  H2 Course/Unit     ffb60d40ac5d89810b95
  H2 Assess Type     6886a1400b54c4efbc20
  rdlVisual          2be39a89865b001608b6
                     reportId = 43a35555-38c4-4b20-85e7-1f9784889cad

ord 13 (Question Response Analysis by Standard and Teacher):
  KPI strip          b8037c56b80e87dbd87e
  H1 banner          4a547fbfe3512c6743f3
  actionButton       e48dd0a52cfcdf718b20
  textbox            2ede279dc0e0af2c8257
  logo               7ede530287ee4452767e
  H2 Course/Unit     e5ea13d59a69d4846e5b
  H2 Assess Type     94cf6be5de40f96c4cdc
  rdlVisual          059957977702b13edd39
                     reportId = 0ffc8105-9687-4175-b14a-599466c1627e

workspaceId (all three): 8215049c-ebd6-4a9b-bb98-5b5fdb7d3da4
```

## Appendix B — Field-name to PBIX-binding cross-reference

Field paths as written in `22_fields_per_page.json:426-624`:

```
Question Response Analysis (ord 11):
  SchoolLogo_Parameter.SchoolLogo_Parameter
  Titles.H1 - Longitudinal
  Titles.H2 Course and Unit
  Titles.H2 - Assessment Type
  Key Measures.Total Questions
  Key Measures.Total Students
  Key Measures.Score
  Sum(Student Submissions.Points Possible)
  Key Measures.% of Correct Answers
  dim_item.assessment_date
  dim_subject.Assessment_type
  dim_item.Item_Name
  dim_subject.Grade
  dim_subject.Subject
  cube_question_summary_overall.Subject_ID
  Titles.H3 - Teachers           (= Titles.Instructor(s):)

Question Response Analysis by Teacher (ord 12):
  Titles.H1 - Longitudinal
  Titles.H2 Course and Unit
  Titles.H2 - Assessment Type
  Key Measures.Total Questions
  Key Measures.Total Students
  Key Measures.Score
  Sum(Student Submissions.Points Possible)
  Key Measures.% of Correct Answers
  dim_item.Item_ID
  dim_item.Item_Name
  dim_subject.Grade
  dim_subject.Subject
  dim_subject.Assessment_type
  dim_subject.Session
  SchoolLogo_Parameter.SchoolLogo_Parameter

Question Response Analysis by Standard and Teacher (ord 13):
  -- identical to ord 12 --
  Titles.H1 - Longitudinal
  Titles.H2 Course and Unit
  Titles.H2 - Assessment Type
  Key Measures.Total Questions
  Key Measures.Total Students
  Key Measures.Score
  Sum(Student Submissions.Points Possible)
  Key Measures.% of Correct Answers
  dim_item.Item_ID
  dim_item.Item_Name
  dim_subject.Grade
  dim_subject.Subject
  dim_subject.Assessment_type
  dim_subject.Session
  SchoolLogo_Parameter.SchoolLogo_Parameter
```

## Appendix C — Working artifacts

Working notes / extracts used to produce this document:

- `/Users/mac/Desktop/PS_P/gains-platform/.planning/reports-expansion/qra-paginated-notes/extract.py` — extractor script
- `/Users/mac/Desktop/PS_P/gains-platform/.planning/reports-expansion/qra-paginated-notes/ord11_qra.json` — flat-extract of all 8 visuals on ord 11
- `/Users/mac/Desktop/PS_P/gains-platform/.planning/reports-expansion/qra-paginated-notes/ord12_qra_by_teacher.json` — same for ord 12
- `/Users/mac/Desktop/PS_P/gains-platform/.planning/reports-expansion/qra-paginated-notes/ord13_qra_by_std_teacher.json` — same for ord 13

Source PDFs used for cross-check:

- `data/sample reports/Paginated - Question Response Analysis.pdf` (8 pages)
- `data/sample reports/Paginated - Question Response Analysis By  Teacher.pdf` (30 pages)
- `data/sample reports/Paginated - Question Response Analysis By Standard And Teacher.pdf` (14 pages)
