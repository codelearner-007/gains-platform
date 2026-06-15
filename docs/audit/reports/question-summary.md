# Question Summary Report — Implementation Spec (3 paginated variants)

> **Scope:** three PBIX *paginated* pages in `data/Assessment Analysis Dashboard.pbix`
> that all render the SAME underlying tablix (student × question matrix) via
> Power BI's **paginated (RDL) embed**, distinguished only by a couple of
> presentation deltas:
>
> | # | PBIX page name                                              | ord | PDF sample                                                       | external RDL `reportId`                |
> |---|-------------------------------------------------------------|----:|------------------------------------------------------------------|----------------------------------------|
> | 1 | `Question Summary Report`                                   |   6 | `Paginated - Question Summary Report (1).pdf`                    | `c037c229-e9d1-46cb-bd01-8dcc946be065` |
> | 2 | `Question Summary Report - teacher subtotal`                |   7 | `Paginated - Question Summary Report - Teacher.pdf`              | `93233571-b9e5-423b-9170-69184c5c2708` |
> | 3 | `Question Summary Report - header highlights`               |  16 | `Paginated - Question Summary Report - color.pdf`                | `15fcb757-465e-4037-b414-72a23ea578eb` |
>
> **Critical architectural note before you read further.** What lives in PBIX
> for these three pages is a tiny **shell page**: 8–9 visuals total, ~95% of
> them being the report-wide *chrome* (logo, header textbox, action button,
> three Title cards, a hidden KPI multiRowCard). The actual report — the
> Classroom-Instructor → Student → per-Question matrix with green/pink/yellow
> conditional cell fills — is a separate **Power BI Paginated (RDL) report**
> embedded via a single `rdlVisual` at `(11, 127, 1256×577)` on each shell
> page. The PBIX shell only passes six parameters (`Item_ID`, `Item_Name`,
> `Subject`, `Grade`, `Session`, `Assessment_type`) to that external RDL via
> `parameterMapping`. The RDL itself is not extracted by `_extract.py` — it
> lives on the Power BI Service workspace
> `8215049c-ebd6-4a9b-bb98-5b5fdb7d3da4` (`Question Summary Report redacted`
> uses a different workspace `cc11f76e-bf13-4c9c-a5f9-a1adaa9d5a0f`).
> Everything we know about the tablix structure, the column hierarchy
> (Standard → Question No), the per-cell colors, and the grand-total row
> therefore comes from the **rendered sample PDFs**, not from the layout JSON.
>
> Treat the PBIX layout as the **outer chrome spec** (header, logo, page
> filter, KPI strip semantics) and the PDFs as the **inner tablix spec**.
>
> **Audience:** implementer building the Next.js + FastAPI replica that
> replaces both the shell *and* the external RDL with one cohesive web report.
> Target route: `frontend/src/app/app/reports/question-summary/page.tsx`
> (one route + `?variant=base|teacher|color` query param — see §SB).

---

## §0 Source-of-truth references

| What                                          | Where                                                                                                                                                                                                                          |
|-----------------------------------------------|--------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------|
| Page summaries (visual types, fields)         | `data/_pbix_extract/20_pages.md:128-180` (ord 6), `:155-180` (ord 7), `:345-371` (ord 16)                                                                                                                                       |
| Full layout JSON (positions, configs, filters)| `data/_pbix_extract/_layout.full.json:527-619` (ord 6 page), `:621-714` (ord 7 page), `:1291-1392` (ord 16 page)                                                                                                                |
| Fields per page                               | `data/_pbix_extract/22_fields_per_page.json:115-176` (ord 6), `:178-241` (ord 7), variants share fields                                                                                                                          |
| DAX measures                                  | `data/_pbix_extract/04_dax_measures.dax` — `Total Student:134`, `Total Question:148`, `Grade Average:168`, `Grade_Average_Standard_Measure:215`, `Performance Color Standard:250`, `Total Possible Point:461`, `% Correct Answer:475`, `Score:482`, `H1 - Longitudinal:656`, `H2 - Assessment Type:320`, `H2 - Course and Unit:340` |
| Tables universe                               | `data/_pbix_extract/02_tables.json` — note: **no `Key Measures` table**, **no `Student Submissions` table** in the PBIX model (see §3.6 quirk)                                                                                  |
| Schema (columns + types)                      | `data/_pbix_extract/03_schema.csv` — `cube_question_summary:30-69`, `cube_question_summary_overall`, `dim_item`, `dim_subject`, `fact_student_submission:188-222`                                                               |
| Rendered samples                              | `data/sample reports/Paginated - Question Summary Report (1).pdf`, `… - Teacher.pdf`, `… - color.pdf` — extracted text in `.planning/reports-expansion/qsr-notes/qsr_*.txt`                                                     |
| Reference spec at matching depth              | `data/_pbix_extract/55_standard_summary_spec.md` (Standard Summary) — this file mirrors its structure                                                                                                                            |

---

## §1 Shared base (all three variants)

The three pages are **byte-for-byte identical at the shell-visual level**
except for one z-stacked action button on ord 16. Document the shell once
here; per-variant sections (§2A/§2B/§2C) only enumerate deltas.

### 1.1 Page-level metadata (all three)

| Property        | ord 6 (base)                              | ord 7 (teacher)                          | ord 16 (header highlights)               |
|-----------------|-------------------------------------------|------------------------------------------|------------------------------------------|
| `id`            | `282753158`                                | `282753159`                               | `282753160`                               |
| `name` (intern.)| `51115437aefe99d2d943`                    | `d50c0fae51c10fcdd038`                   | `c50cf2b1161f7fb0eedb`                   |
| `objectId`      | `b848c355-ecbb-428b-850a-7e440bd91002`     | `0370ac91-398f-44d2-ac5a-d4b991242cba`    | `5bda600e-d7a1-4ca2-8d47-0949bafb6531`    |
| `displayName`   | `Question Summary Report`                  | `Question Summary Report - teacher subtotal` | `Question Summary Report - header highlights` |
| `ordinal`       | `6`                                        | `7`                                       | `16`                                      |
| Canvas          | 1280 × 720                                 | 1280 × 720                                | 1280 × 720                                |
| `displayOption` | `1` (Fit-to-page interactive)              | `1`                                       | `1`                                       |
| Page background | `#CACEDA` (`outspace`)                     | `#CACEDA`                                 | `#CACEDA`                                 |
| Page width hint | `outspacePane.width = 198L` (line 615)     | (none)                                    | `outspacePane.width = 198L` (line 1491)   |
| Visual count    | 8                                          | 8                                         | 9 (extra `actionButton`)                  |

### 1.2 Shared shell visuals — 7 of 8

The seven chrome visuals appear in all three pages with the SAME geometry and
SAME config. Indexing uses the position in each page's `visualContainers`
array (0-indexed). IDs differ per page (they are auto-incremented by PBIX).

| # | Type / Visual                                   | Pos (x, y, w, h)              | z      | Notes                                                                                  |
|---|-------------------------------------------------|-------------------------------|-------:|----------------------------------------------------------------------------------------|
| #0 | `multiRowCard` — `Titles.H1 - Longitudinal`    | 120.93, 10.96, 490.19 × 40.28 | 7000 (ord 6/7), 8000 (ord 16) | Renders the string `"Paginated PDF Report \|"`. `cardTitle.fontSize=18D`, theme color 1. Title hidden. |
| #1 | `multiRowCard` — `Titles.H2 - Course and Unit` | 122.07, 58.18, 582.96 × 39.93 | 1000   | Renders `"Course: <Grade>: <Item_Name>"` (e.g., `Grade 1: Tell Me a Story: Weekly Assessment: Week 2`). `cardTitle.fontSize=16D`, theme color 2 darker −0.5. Filter forces only one row. |
| #2 | `multiRowCard` — `Titles.H2 - Assessment Type` | 122.07, 88.98, 499.68 × 38.79 | 2000   | Renders `"Lesson Assessments"` (or whatever `dim_subject.Assessment_type` resolves to). `cardTitle.fontSize=14D`. |
| #3 | `textbox` — static "Question Summary Report"   | 346.74, 17.25, 679.68 × 37.09 | 3000   | The big H1 title. `text:'Question Summary Report'` (ord 6), `'Question Summary Report - Teacher Subtotal'` (ord 7), `'Question Summary Report - header highlights'` (ord 16). fontSize 17D, left-aligned, theme color 1. Background transparent. |
| #4 | `multiRowCard` (HIDDEN) — Key Measures KPIs    | 528.55, 0, 533.89 × 48.05     | 0      | `"display":{"mode":"hidden"}` (line 577 / 671 / 1349). Authors-only KPI binding. Holds 5 measures: `Total Questions`, `Total Students`, `Score`, `Sum(Points Possible)`, `% of Correct Answers`. Ordered desc by `Total Questions`. **Not rendered.** |
| #5 | `rdlVisual` — embedded paginated report        | 11, 127, 1256 × 577           | 4000 (ord 6/7), 5000 (ord 16) | THE actual report (see §3). Border on, radius 16D, drop shadow on, header off, background transparency 66D. |
| #6 | `simpleImage...` — `SchoolLogo_Parameter`      | 27.74, 17.46, 76.02 × 71.91   | 5000 / 6000 | Top-left school logo. `SchoolLogo_Parameter.SchoolLogo_Parameter` is a Power Query Parameter (M file `07_power_query.m`). Background off. |
| #7 | `actionButton` — blank navigation              | 28.16, 15.54, 81.58 × 73.81   | 6000 / 7000 | Transparent invisible button overlaying the logo. `visualLink.show=true`. Wired to navigate back to Home. Icon hidden. |

#### 1.2.1 H1 / H2 measure formulas (verbatim from `04_dax_measures.dax`)

```dax
// 04_dax_measures.dax:656
MEASURE [H1 - Longitudinal] =
"Paginated PDF Report |"
```

```dax
// 04_dax_measures.dax:340
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
// 04_dax_measures.dax:320
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

Both `H2 - Course and Unit` and `H2 - Assessment Type` carry a self-referential
visual-level filter (e.g., `_layout.full.json:548`, `:558`) of type
`Advanced` / `isHiddenInViewMode:true` whose only purpose is to enforce that
the measure's value is non-blank — a Power BI authoring trick to suppress
empty cards. We do not need to replicate this in the React component;
`!!value && <Card>` handles it.

### 1.3 Hidden KPI multiRowCard (#4 above) — projections

The visual is hidden (`display.mode:"hidden"`, `_layout.full.json:577`,
`:671`, `:1349`) so it never renders in the PBIX shell. It exists as a
**data dependency declaration** — when published, the PBIX engine wires those
five measures into the dataset so the external RDL can read them. The
projections are:

| `queryRef`                                  | Resolves to (model)                                  | Meaning                          |
|---------------------------------------------|------------------------------------------------------|----------------------------------|
| `Key Measures.Total Questions`              | (renamed/aliased — see §3.6)                         | Count of distinct questions      |
| `Key Measures.Total Students`               | (renamed/aliased — see §3.6)                         | Count of distinct students       |
| `Key Measures.Score`                        | (renamed/aliased — see §3.6)                         | Sum of points earned             |
| `Sum(Student Submissions.Points Possible)`  | `SUM(fact_student_submission.Points_Possible)` (aliased) | Total possible points          |
| `Key Measures.% of Correct Answers`         | (renamed/aliased — see §3.6)                         | Total score / total possible     |

`OrderBy: Direction=2` (descending) on `Total Questions`. Default sort flag
on (`hasDefaultSort:true`).

**Closest matching DAX measures in the actual model** (`04_dax_measures.dax`):

```dax
// 04_dax_measures.dax:148   ←  Total Questions
MEASURE [Total Question] =
DISTINCTCOUNT('cube_question_summary_overall'[Question_No])

// 04_dax_measures.dax:134   ←  Total Students
MEASURE [Total Student] =
SUMX(
    SUMMARIZE(
        'cube_school_summary',
        'cube_school_summary'[Item_ID],
        "UniqueTotalQuestions", MAX('cube_school_summary'[Total_Students])
    ),
    [UniqueTotalQuestions]
)

// 04_dax_measures.dax:482   ←  Score
MEASURE [Score] =
SUM('cube_questionincorrectchoice_summary'[Total_Score])

// 04_dax_measures.dax:461   ←  ~ Sum(Student Submissions.Points Possible)
MEASURE [Total Possible Point] =
SUMX(
    SUMMARIZE(
        'cube_question_summary',
        'cube_question_summary'[Question_ID],
        "UniqueTotalQuestions", MAX('cube_question_summary'[Total_Possible_Point])
    ),
    [UniqueTotalQuestions]
)

// 04_dax_measures.dax:475   ←  % of Correct Answers
MEASURE [% Correct Answer] =
AVERAGE('cube_question_summary_overall'[Grade_Average])
```

### 1.4 `rdlVisual` (#5) — parameters passed to the external RDL

All three pages declare the **same six query refs**, mapped to RDL parameter
names via `parameterMapping`. (`_layout.full.json:587`, `:681`, `:1359`.)

| RDL parameter (`paramName`)     | Bound field             | `isMultiValue` |
|---------------------------------|-------------------------|:--------------:|
| `cubeuserssummaryItemName`      | `dim_item.Item_Name`    | true           |
| `cubeuserssummaryItemID`        | `dim_item.Item_ID`      | true           |
| `cubeuserssummaryGrade`         | `dim_subject.Grade`     | true           |
| `cubeuserssummarySubject`       | `dim_subject.Subject`   | true           |
| `cubeuserssummarySession`       | `dim_subject.Session`   | true           |
| `cubeuserssummaryAssessmenttype`| `dim_subject.Assessment_type` | true     |

> The `cubeuserssummary…` prefix is a smoking-gun: the external RDL hits a
> table called `cube_users_summary` (which is **not in the PBIX model** —
> see `02_tables.json` for the in-model universe). `cube_users_summary` is
> the unredacted student-grain users cube; the "redacted" variant on ord 17
> binds the same parameters but to a redacted projection of the same cube
> (`_layout.full.json:1483`). For our rebuild, `cube_users_summary` maps to
> the platform's existing per-(item, user, question) repository view —
> see §3.5.

`autoFilter.show=true` (ord 6 line 587, ord 16 line 1359 — **absent** on
ord 7 line 681). That filter lets the user re-filter the embedded RDL at
runtime via Power BI's filter pane.

`reportInfo.reportId` is the GUID of the external RDL (see header table at
the top of this file). `reportInfo.workspaceId` is the host Power BI Service
workspace; the redacted variants live in a different workspace.

### 1.5 Page-level filter — the assessment scoping `Item_Name`

All three pages have **one categorical page filter on `dim_item.Item_Name`**
that pins the page to ONE assessment, baked into the saved PBIX (this
mirrors the SDD pattern at `50_sdd_spec.md`).

| Page  | Filter name                  | `Item_Name` value (literal)                                          |
|-------|------------------------------|----------------------------------------------------------------------|
| ord 6 | `5cf3eed1ff26fed7445e`       | `'Module 7 Test'`                                                    |
| ord 7 | `a68ba9c1067093c125be`       | `'What Makes Us Who We Are?: Weekly Assessment: Week 2'`             |
| ord 16| `a68ba9c1067093c125be`       | `'Module 1 Test'`                                                    |

Each page also has a SECOND categorical filter on `Item_Name` of type
`Categorical, howCreated:5` with NO `Where` clause — this is a "filter card
placeholder" that allows the user to override the bake (see
`_layout.full.json:612`, `:706`, `:1384`).

> **Implication for rebuild:** the assessment to render is selected by the
> caller via `?item_id=<uuid>` in our URL, exactly like SDD. There is no
> page-baked filter in our React route — the React component takes
> `item_id` as a query param.

> **Note (PDFs vs PBIX bake):** the sample PDFs in `data/sample reports/`
> were all rendered against the **same** item — `Tell Me a Story: Weekly
> Assessment: Week 2`. The PBIX itself has each page baked to a DIFFERENT
> assessment; the PDFs in the repo were generated after the rebuild
> exercise pinned all three to the same item for direct comparison.

### 1.6 Shared Title-table dependencies (the `Titles` calculated table)

The PBIX has a calculated table `Titles` (`06_dax_tables.csv` references all
`Titles[*]` measures). The three measures used on the shell are all in
that table (note: `H1 - Longitudinal` is a `Measure`-table member but is
referenced by `Titles.H1 - Longitudinal` in the page query — Power BI does
not require the table-namespace to match the actual storage table; the
namespace is a *display* label set in the modeller).

---

## §2A Variant 1 — `Question Summary Report` (ord 6, base)

### 2A.1 Purpose

The "vanilla" Question Summary view. For a single assessment, render every
student's per-question result as a binary matrix (0/1), grouped by Classroom
Instructor, with a Score % column per student and grand totals at the very
end. The **default** report used for parent-facing class-level analytics.

**Audience:** classroom teachers, curriculum leads.
**Decision driver:** "for THIS assessment, which questions did each student
get right/wrong, and which questions did the whole class struggle with?"

### 2A.2 Page geometry

- Canvas 1280 × 720; 8 visuals.
- Shell visuals exactly as listed in §1.2.
- The `rdlVisual` occupies `(11, 127) → (1267, 704)` — 1256 × 577 px — at
  z=4000.

### 2A.3 Layout map (per-PDF tablix)

The PDF (`Paginated - Question Summary Report (1).pdf`) reveals the embedded
tablix structure. The same tablix is used by ord 7 and ord 16; documented
here once and referenced from those sections.

**Tablix structure** — 3 row groups, 2 column groups:

```
                                    [ Standard code group  ── colspan = #questions ]
                                    [ Question No        ── one column per question ]
[ Classroom    [ Student Name [ Score %  | <0/1>  <0/1>  <0/1>  …  | Possible | # Correct |
[ Instructor   [              [          |                          | Points   | Answers   |
[              ───── per-student rows ──────────────────────────────────────────
[ <next teacher group> ──────────────────────────────────────────────────────────
…
[ GRAND TOTAL ROWS (base variant only at end of report) ────────────────────────
        Possible Points       <total possible per question column> <grand total possible> <grand total correct>
        # Correct Answers     <correct count per question column>
        Score %               <pct correct per question column>
```

**Row groups (outer → inner):**
1. **Classroom Instructor** (`fact_student_submission.Section_Instructors` /
   `cube_question_summary.Section_Instructors`) — group header cell shows
   the instructor name AND the per-teacher Score % stacked vertically
   (e.g., `Elizabeth Sedlak` / `77.8%`). The 77.8% is the teacher-class
   average across all students in that group.
2. **Student Name** (`fact_student_submission.User_Name`) — one row per
   student, sorted ascending by **Score %** (low → high). Confirmed from
   PDF page 1: 45%, 45%, 50%, 59%, 77%, 77%, 77%, 82%, 86%, 86%, 91%, 91%,
   91%, 95%, 95%, 95%.
3. *(implicit per-student totals row inside each student row — not a group)*

**Column groups (outer → inner):**
A. **Standard code** (`cube_question_summary_overall.Standards` or
   `dim_standard.cPalms_Standard`) — header row at the top of the tablix.
   Each cPalms code spans `colspan = number of questions tagged to that
   standard`. Codes seen on PDF page 1: `ELA.1.C.3.1` (2), `ELA.1.F.1.3.c` (2),
   `ELA.1.F.1.4.a` (3), `ELA.1.R.1.1` (10), `ELA.1.R.1.2` (1), `ELA.1.R.3.1`
   (1), `ELA.1.V.1.2` (1), `ELA.1.V.1.3` (2).
B. **Question No** (`cube_question_summary_overall.Question_No` /
   `Position_Number`) — leaf column header, one integer per question.
   Order: **question number ascending within each standard** — verified
   against the PDF (`11, 12 | 8, 9 | 6, 7, 10 | 1, 2, 4, 13, 15, 16, 18, 19,
   21, 22 | 17 | 20 | 5 | 3, 14`). Questions are pre-grouped by standard,
   not in raw 1-N order.

**Static (non-grouped) columns at fixed positions:**
- Col 1 `Classroom Instructors` — first row-group header column
- Col 2 `Student Name` — second row-group header column
- Col 3 `Score %` — per-student grand-row %; formatted `"0%"`
- … per-question cells (one per leaf column group instance) …
- Last 2 cols `Possible Points`, `# Correct Answers` — per-student row
  totals (e.g., `22`, `10` for Harper Kuhn)

**Grand-total tablix footer (BASE VARIANT — appears once, at end of report):**
| Row label          | Score %            | per-question values                          | Possible Points | # Correct Answers |
|--------------------|--------------------|----------------------------------------------|----------------:|------------------:|
| `Possible Points`  | `1166`             | `53` (= # students who attempted, per Q)    | `1166`          | `953`             |
| `# Correct Answers`| `953`              | per-question correct count (e.g. `49 42 52 …`) | (blank)       | (blank)           |
| `Score %`          | `82%`              | per-question pct (`92% 79% 98% 100% …`)     | (blank)         | (blank)           |

> The grand-total footer shows `# students × Possible Points = 53 × 22 = 1166`
> and `# correct cells = 953` ⇒ overall `953/1166 = 81.7%` ≈ rounded `82%`.

### 2A.4 Field bindings (the rdlVisual's six parameters)

| Tablix column / cell                           | Source field                                                |
|------------------------------------------------|-------------------------------------------------------------|
| Classroom Instructor (row group)               | `cube_users_summary.Section_Instructors` (or `cube_question_summary.Section_Instructors:66`) |
| Student Name (row group)                       | `cube_users_summary.User_Name` (or `fact_student_submission.User_Name:220`) |
| Score % per student                            | `SUM(Points_Received) / SUM(Points_Possible)` per `User_UID` |
| Score % per teacher (group header)             | same as above, aggregated over the group's `User_UID`s     |
| Standard column header                         | `cube_question_summary_overall.Standards` → joined to `dim_standard.cPalms_Standard` |
| Question No column header                      | `cube_question_summary_overall.Question_No`                |
| Per-cell 0/1                                   | `fact_student_submission.Points_Received` (binary fold to {0,1} via `IF Points_Received > 0`). For multi-select questions this should be `Submission_Grade` or a per-cell `Score / Possible` ratio — verify against legacy spec. |
| Possible Points (per-student col)              | `SUM(Points_Possible)` over the student's submissions      |
| # Correct Answers (per-student col)            | `SUM(Points_Received)` over the student's submissions      |
| `Possible Points` (grand total row)            | `SUM(Points_Possible)` over all (user, question)            |
| `# Correct Answers` (grand total row)          | `SUM(Points_Received)` over all (user, question)            |
| `Score %` (grand total row)                    | `SUM(Points_Received) / SUM(Points_Possible)`               |

### 2A.5 DAX measures used (verbatim)

The rdlVisual itself executes its computation **inside the external RDL**,
not via PBIX DAX. However, the hidden KPI multiRowCard (#4 above) declares
the following five DAX dependencies that are equivalent in semantics. Paste
these verbatim from `04_dax_measures.dax`:

```dax
// 04_dax_measures.dax:148
MEASURE [Total Question] =
DISTINCTCOUNT('cube_question_summary_overall'[Question_No])

// 04_dax_measures.dax:134
MEASURE [Total Student] =
SUMX(
    SUMMARIZE(
        'cube_school_summary',
        'cube_school_summary'[Item_ID],
        "UniqueTotalQuestions", MAX('cube_school_summary'[Total_Students])
    ),
    [UniqueTotalQuestions]
)

// 04_dax_measures.dax:482
MEASURE [Score] =
SUM('cube_questionincorrectchoice_summary'[Total_Score])

// 04_dax_measures.dax:461
MEASURE [Total Possible Point] =
SUMX(
    SUMMARIZE(
        'cube_question_summary',
        'cube_question_summary'[Question_ID],
        "UniqueTotalQuestions", MAX('cube_question_summary'[Total_Possible_Point])
    ),
    [UniqueTotalQuestions]
)

// 04_dax_measures.dax:475
MEASURE [% Correct Answer] =
AVERAGE('cube_question_summary_overall'[Grade_Average])
```

Three additional measures are used on the shell (Titles):

```dax
// 04_dax_measures.dax:656
MEASURE [H1 - Longitudinal] = "Paginated PDF Report |"

// 04_dax_measures.dax:320  (full body cited in §1.2.1)
MEASURE [H2 - Assessment Type] = …

// 04_dax_measures.dax:340  (full body cited in §1.2.1)
MEASURE [H2 - Course and Unit] = …
```

### 2A.6 Row grouping / totals

- **Row groups:** Classroom Instructor → Student Name (2 levels).
- **Subtotal rows (per group):** **NONE in the base variant.** The
  per-teacher Score % shown in the group-header cell is a label, not a
  subtotal row. The teacher subtotal variant (§2B) ADDS such subtotal rows.
- **Grand total row (table footer):** YES — three rows: `Possible Points`,
  `# Correct Answers`, `Score %`. Each row spans all per-question columns
  PLUS the last two static cols. Visible only on the LAST page of the
  multi-page render.
- **Sort order within Student Name group:** ASC by Score % (lowest first).
- **Sort order of Classroom Instructor groups:** alphabetical by instructor
  name (verified from PDF: Elizabeth Sedlak → Mason Reeder → Taylor
  Almendinger).
- **Sort order of column groups (standards):** appears to be by
  `Position_Number` of the FIRST question in the standard, ascending — i.e.,
  the natural-order grouping.

### 2A.7 Conditional formatting (cell coloring)

> ⚠️ The conditional rules are **defined inside the external RDL** (the
> `.rdl` file in the Power BI workspace), not in `_layout.full.json`.
> The PBIX shell can't see them. The rules below are reverse-engineered
> directly from the rendered PDF and match the same three-band logic
> documented in `55_standard_summary_spec.md §6` and the
> `Performance Color Standard` DAX measure at `04_dax_measures.dax:250-266`.

**Per-cell coloring (the 0/1 student × question cells):**

| Value of cell    | Fill                                                  |
|------------------|-------------------------------------------------------|
| `1` (correct)    | `#00FF06` (green) — equivalent to `PERF_GREEN`        |
| `0` (incorrect)  | `#FFCCFF` (pink)  — equivalent to `PERF_PINK`         |
| missing / null   | grey / theme default                                  |

> The cell coloring on the standard cPalms code header is the **header
> highlights** variant's distinguishing feature — see §2C. In the base
> variant, the standard-code header bar is a uniform navy/blue (`#4472C4`
> Office-theme accent 1, with white text). The Question No row below it
> is a slightly lighter blue (`#8FAADC` accent 1 −0.25).

**Per-student Score % column (the third static column) — base variant:**
this column gets a three-band fill based on the student's score:

| Score % range     | Fill          |
|-------------------|---------------|
| `< 70%`           | `#FFCCFF` (pink) — matches "below grade level" |
| `70% ≤ x < 80%`   | `#FFFF00` (yellow) — note: `Performance Color Standard` (`04_dax_measures.dax:262`) uses the named color `"Yellow"` which the legacy renderer maps to `#FFFF00`. The `Grade_Average_Standard_Measure` inline-switch on the SDD page uses `#faff00` — pick one and apply consistently. The PDF render appears closer to `#FFFF00`. |
| `≥ 80%`           | `#00FF06` (green) |
| `0` exactly       | uncolored / theme default |

**Per-teacher Score % (in the group-header cell, e.g., `77.8%`):** appears
**uncolored** in the base variant — the highlight goes on the per-student
row only. (Compare PDF page 1: `Elizabeth Sedlak / 77.8%` is on white;
the row-Score-%s `45% 45% 50% 59% …` ARE colored.)

**Verbatim DAX (the three-band rule we mirror):**

```dax
// 04_dax_measures.dax:250
MEASURE [Performance Color Standard] =

VAR High = 0.8
VAR Low = 0.7

VAR Selectedattribute = AVERAGE('cube_question_summary_overall'[Grade_Average])

VAR Result =
        SWITCH(TRUE(),
        Selectedattribute>=High, "#00FF06", //longitudinal green
        AND(Selectedattribute<Low,Selectedattribute>=0), "#FFCCFF",
     //   Selectedattribute<Low, "Red",
        ANd(Selectedattribute>=Low,Selectedattribute<High), "Yellow"
        )

Return
Result
```

### 2A.8 Filters / parameters

**Page-level filter (`_layout.full.json:612`):**

```jsonc
{
  "name": "5cf3eed1ff26fed7445e",
  "expression": { "Column": { "Property": "Item_Name" } },
  "filter": { "Where": [{ "Condition": { "In": {
      "Values": [[{ "Literal": { "Value": "'Module 7 Test'" }}]]
  }}}]},
  "type": "Categorical",
  "howCreated": 5
}
```

Plus an empty filter card placeholder also on `Item_Name`.

**Visual filters:** the rdlVisual itself declares `"filters":"[]"` — no
visual-level filters. The two `H2 - Course and Unit` / `H2 - Assessment Type`
multiRowCards each have a self-referential `Advanced/howCreated:0` filter
on their own measure (the standard non-blank trick).

**RDL parameters:** the six declared in §1.4 above.

**M-parameters (across-page, model-wide — `07_power_query.m`):**
- `SchoolID` — pinned to one school via Power Query parameter; tenant
  isolation is "one PBIX per school", same model as SDD/Standard Summary.
- `SchoolLogo_Parameter` — image URL passed to visual #6.
- `SchoolName_Parameter` — not used on these three pages (visible on the
  Home page).
- `Report Short Name` — drillthrough-table column, not used here.

### 2A.9 PDF cross-check

Confirmed visible from `Paginated - Question Summary Report (1).pdf`:
- Top-left logo (~76 × 72 px, page 1).
- "Question Summary Report" H1 in heavy black serif (~17pt).
- "Lesson Assessments" subheader (the Assessment Type).
- "ELA - Grade 1: Tell Me a Story: Weekly Assessment: Week 2" line below
  in lighter weight (the Course-and-Unit).
- Top horizontal rule (`outspacePane.width=198L` is the slicer-bar
  reservation — not visible on the rendered PDF).
- Repeating tablix header at top of every page: `Classroom Instructors |
  Student Name | Score % | <standard-codes spanning question cols> |
  Possible Points | # Correct Answers`.
- Footer: `Generated at <timestamp> UTC` (left), `Page <n> of <total>`
  (right). The sample PDF spans **9 pages** total.
- Grand total appears at the bottom of **page 8** (rows `Possible Points`,
  `# Correct Answers`, `Score %`).
- Page 9 is a tail page with just the residual columns (`ELA.1.R.1.2`,
  `ELA.1.R.3.1`, `ELA.1.V.1.2`, `ELA.1.V.1.3`) plus their grand totals
  — the column groups wrap across page boundaries (NOT a fixed column
  layout). Implementation note: replicate via horizontal pagination in
  Recharts / react-table when print mode is requested; for screen mode,
  render one wide scrollable table.

---

## §2B Variant 2 — `Question Summary Report - teacher subtotal` (ord 7)

### 2B.1 Purpose

Adds a **per-Classroom-Instructor subtotal row block** at the end of each
teacher's row group. Otherwise identical to §2A.

**Audience:** principals, department heads — anyone who wants to compare
class-level performance per question, side-by-side, without re-aggregating
in their head.

**Decision driver:** "for THIS assessment, how does each teacher's class
compare on a per-question and per-standard basis?"

### 2B.2 Page geometry

Same as §2A — 1280 × 720, 8 visuals, same shell visual configs. Only
deltas are:
- Z-order on the rdlVisual is `4000` (same as base; the higher z=6000 logo
  / 5000 image stack matches base — note the third variant differs on this).
- The `outspace.width=198L` slicer-pane size hint **is absent** here
  (`_layout.full.json:709`) — cosmetic only.
- The textbox title (#3) reads `'Question Summary Report - Teacher Subtotal'`.
- The page filter (`_layout.full.json:706`) bakes a different `Item_Name`
  (`'What Makes Us Who We Are?: Weekly Assessment: Week 2'`) — incidental
  to the sample PBIX, not a structural difference.
- The rdlVisual `parameterValues` array reorders `Session` ahead of
  `Assessment_type` and lists `Item_Name` as `Item_Name1` (`NativeReferenceName`)
  — cosmetic differences in PBIX param-binding, no semantic effect.
- The rdlVisual `autoFilter.show` flag is **absent** here (present on
  variants 1 and 3) — meaning users can't expose the embedded-report
  filter pane.

### 2B.3 Layout map

Same tablix as §2A.3. The only structural delta is in the **subtotal row
section**:

After every Classroom-Instructor group's last student row, the variant adds
TWO subtotal rows:

| Static col 1 / 2     | Score %                 | per-question cells              | Possible Points | # Correct Answers |
|----------------------|-------------------------|---------------------------------|-----------------|-------------------|
| (blank)/`# Correct Answers` | `<sum-correct per teacher>` (e.g. `274`) | per-question correct count for THIS teacher's students (e.g. `15 12 16 16 …`) | (blank)         | (blank)           |
| (blank)/`Score %`    | `<teacher avg %>` (e.g. `78%`) | per-question pct for THIS teacher's students (e.g. `94% 75% 100% 100% …`) | (blank)         | (blank)           |

> Source PDF: `Paginated - Question Summary Report - Teacher.pdf` page 2
> (`Elizabeth Sedlak` group ends with rows `# Correct Answers 274 … ` and
> `Score % 78% …`).

The grand-total row at the end of the report (`Possible Points 1166`,
`# Correct Answers 953`, `Score % 82%`) **is also present**, same as §2A.
This variant therefore has both per-teacher and report-wide totals.

### 2B.4 Field bindings & DAX

Identical to §2A.4 / §2A.5. The per-teacher subtotals reuse the same
underlying fields — the change is purely in the RDL tablix's `<Group>`
configuration: setting `<GroupExpressions>` on the Classroom Instructor
group to ALSO produce a `<Subtotals>` footer aggregation block.

### 2B.5 Row grouping / totals

- **Row groups:** Classroom Instructor → Student Name. **Subtotals
  enabled on the Classroom Instructor group footer** (the structural delta).
- **Per-teacher subtotal block:** 2 rows (`# Correct Answers`, `Score %`)
  per teacher group, inserted between the last student of one teacher and
  the first student of the next.
- **Grand total:** YES (`Possible Points`, `# Correct Answers`, `Score %`
  — same three rows as §2A).

### 2B.6 Conditional formatting

Identical cell colors and three-band Score % to §2A. The new subtotal rows
themselves DO get coloring on the per-question `Score %` cells (visible on
PDF — `94% 75% 100% 100% 94% 94% 100% 50% 63% 81% 88% 81% 88% 69% 69% 69%
63% 44%` — the `50%`, `63%`, `44%` cells render pink, the `81%`+
cells render green, the `75%`/`78%` cells render yellow).

The subtotal `# Correct Answers` row appears **uncolored** (theme grey).
The subtotal label cells (`# Correct Answers`, `Score %`) are on a soft
blue/lavender background — matches the static-column background.

### 2B.7 Filters / parameters

Same as §2A.8 except for the differences noted in §2B.2:
- `autoFilter.show` absent — no embedded-RDL filter pane.
- Different `Item_Name` literal bake.

### 2B.8 PDF cross-check

`Paginated - Question Summary Report - Teacher.pdf` confirms:
- Same header chrome as §2A.
- After each Classroom-Instructor block (e.g., `Elizabeth Sedlak / 77.8%`),
  TWO additional rows appear with labels `# Correct Answers` and `Score %`
  in column 2 (where Student Name would be).
- Column 3 (`Score %` static col) on the `# Correct Answers` subtotal row
  shows the teacher's *correct answer count* (`274`), and on the `Score %`
  subtotal row shows the teacher's *aggregate Score %* (`78%`).
- The grand-total footer at the END of the report has the same shape but
  bigger numbers (`# Correct Answers 953`, `Score % 82%`).

---

## §2C Variant 3 — `Question Summary Report - header highlights` (ord 16)

### 2C.1 Purpose

Same tablix as §2A but with **conditional fill applied to the Standard
Code header cells** at the top of the tablix. Each cPalms-code header tile
takes a green / yellow / pink background based on the **per-standard
school-wide average score** on that standard.

**Audience:** anyone briefing the school's standards-level health at a glance
— a single look at the colored header strip tells you which standards the
class crushed (green) vs needs reteach (pink).

**Decision driver:** "for THIS assessment, which standards is the class
strongest / weakest on?" The header-strip color answers that without
reading any per-student rows.

### 2C.2 Page geometry

- Canvas 1280 × 720; 9 visuals (one extra `actionButton`).
- Shell visuals as in §1.2 except:
  - One additional `actionButton` (`8695561831`, `_layout.full.json:1334`)
    at `(21.68, 20.53, 82.14×73.01)`, z=4000. Functionally identical to
    visual #7 (transparent, `visualLink.show=true`, blank shape). Likely a
    second invisible nav button overlaid on the title bar — could be a
    duplicate authoring artefact (the icon overlay differs only by 6 px).
  - The rdlVisual is at z=`5000` (was 4000 in §2A) because the extra
    actionButton bumped the z-stack.
  - Textbox title (#3) reads `'Question Summary Report - header highlights'`.

### 2C.3 Layout map

Identical tablix to §2A. The structural delta is **purely in the
conditional formatting** of the column-group header cells — see §2C.6.

### 2C.4 Field bindings & DAX

Identical to §2A.4 / §2A.5.

### 2C.5 Row grouping / totals

- **Row groups:** Classroom Instructor → Student Name (2 levels). No
  per-teacher subtotal rows (this variant does NOT pick up the §2B subtotal
  block — confirmed against `qsr_color.txt`).
- **Grand total at end:** YES — same three rows as §2A.

### 2C.6 Conditional formatting (the critical delta vs §2A)

The Standard Code column-header cells (the top row of the tablix that spans
N question-columns per standard) carry a three-band fill:

| Per-standard avg score (`AVG(grade_average) WHERE Standards = X`)| Header fill   |
|--------------------------------------------------------|---------------|
| `< 70%`                                                | `#FFCCFF` pink |
| `70% ≤ x < 80%`                                        | `#FFFF00` yellow |
| `≥ 80%`                                                | `#00FF06` green |

Verified from the PDF page 1 screenshot of the color variant:
- `ELA.1.C.3.1` header: green (class avg high — confirms ~94%/79% column
  averages from the grand total)
- `ELA.1.F.1.3.c` header: green
- `ELA.1.F.1.4.a` header: green (with one cell yellow `94%`)
- `ELA.1.R.1.1` header: yellow (the long-span standard sits in 70–80%)

The Question No row below the Standard Code row remains uncolored (or
inherits a faint background).

**DAX equivalent for the per-standard color:**

```dax
// 04_dax_measures.dax:215
MEASURE [Grade_Average_Standard_Measure] =
AVERAGE('cube_question_summary_overall'[Grade_Average])

// 04_dax_measures.dax:250 (re-paste for completeness; same as §2A.7)
MEASURE [Performance Color Standard] =

VAR High = 0.8
VAR Low = 0.7

VAR Selectedattribute = AVERAGE('cube_question_summary_overall'[Grade_Average])

VAR Result =
        SWITCH(TRUE(),
        Selectedattribute>=High, "#00FF06",
        AND(Selectedattribute<Low,Selectedattribute>=0), "#FFCCFF",
        ANd(Selectedattribute>=Low,Selectedattribute<High), "Yellow"
        )

Return
Result
```

The per-cell (student × question) 0/1 coloring (green/pink) and the
per-student Score % column three-band coloring remain identical to §2A.7.

### 2C.7 Filters / parameters

Same as §2A.8 except for the `Item_Name` literal bake = `'Module 1 Test'`
(`_layout.full.json:1384`). `autoFilter.show=true` is present, matching
the base variant.

### 2C.8 PDF cross-check

`Paginated - Question Summary Report - color.pdf` confirms:
- Standard Code header cells visibly tinted green/yellow.
- All other rules from §2A reproduced exactly.
- An empty space appears under the `actionButton` overlay (cosmetic only,
  not a rendering bug — the duplicate transparent button is invisible by
  design).

---

## §SB Shared base & deltas — implementation strategy

### SB.1 What the three variants share (structurally identical)

| Layer                                       | Same?  | Source                                       |
|---------------------------------------------|:------:|----------------------------------------------|
| Shell visuals (#0 – #4, #6, #7)              | YES    | `_layout.full.json:527-619` etc.             |
| `rdlVisual` parameter mapping (6 params)     | YES    | `_layout.full.json:587` `:681` `:1359`       |
| Page filter on `dim_item.Item_Name`         | YES (different literals — see header table) | line 612 / 706 / 1384 |
| Underlying data source (`cube_users_summary`) | YES   | RDL parameter prefix `cubeuserssummary*`    |
| Tablix structure (row groups, column groups) | YES   | reverse-engineered from all 3 PDFs           |
| Per-student row sort (asc by Score %)        | YES   | PDF observation                              |
| Cell-level 0/1 coloring (green/pink)         | YES   | PDF observation                              |
| Per-student Score % 3-band coloring          | YES   | PDF observation                              |
| Grand-total footer rows                      | YES   | PDF observation (last page of each PDF)      |
| KPI measure dependency set                  | YES   | hidden multiRowCard projections              |

### SB.2 What CHANGES between variants — the only three deltas

| Delta                                             | base (§2A) | teacher (§2B) | color (§2C) |
|---------------------------------------------------|:----------:|:-------------:|:-----------:|
| Title text                                        | `"Question Summary Report"` | `"Question Summary Report - Teacher Subtotal"` | `"Question Summary Report - header highlights"` |
| **Per-teacher subtotal rows (after each group)**  | NO         | **YES**       | NO          |
| **Standard Code header cells colored**            | NO (solid navy) | NO (solid navy) | **YES (3-band)** |
| Extra actionButton on shell                       | NO         | NO            | YES (+1)    |
| `rdlVisual.autoFilter.show`                       | true       | absent (false) | true       |
| RDL `reportId`                                    | `c037c229…` | `93233571…`  | `15fcb757…` |

That's it. Everything else is byte-for-byte the same.

### SB.3 Recommendation: ONE React component with variant flags

> **Single component**, not three. The shared surface is ~98% of the code.

Sketch:

```typescript
// frontend/src/components/app/modules/reports/question-summary/QuestionSummaryReport.tsx
type Variant = 'base' | 'teacher' | 'color';

interface Props {
  itemId: string;
  variant?: Variant;  // default 'base'
}

export function QuestionSummaryReport({ itemId, variant = 'base' }: Props) {
  const { data } = useQuery(reportsKeys.questionSummary(itemId), () =>
    reportsApi.questionSummary(itemId)
  );
  // … render shell (logo, title, course-and-unit, assessment-type)
  // … render single matrix table:
  return (
    <QuestionSummaryMatrix
      rows={data.rows}                     // grouped: instructor[].students[].cells[]
      standards={data.standards}            // column group A
      questions={data.questions}            // column group B
      grandTotals={data.grandTotals}
      colorHeaders={variant === 'color'}    // §2C delta
      teacherSubtotals={variant === 'teacher'}  // §2B delta
      title={titleFor(variant)}
    />
  );
}
```

Three Next.js routes share the component:
- `frontend/src/app/app/reports/question-summary/page.tsx?item_id=…&variant=base`
- `frontend/src/app/app/reports/question-summary/page.tsx?item_id=…&variant=teacher`
- `frontend/src/app/app/reports/question-summary/page.tsx?item_id=…&variant=color`

OR a single page that exposes a tab switcher (recommended UX — same data
payload, three views).

The **backend payload is identical for all three variants** (the
per-teacher subtotals and per-standard averages can be computed
client-side from the base matrix, OR pre-aggregated on the server once).
There is no reason to ship three different endpoints.

### SB.4 Suggested data shape

```python
class QuestionSummaryRow(BaseModel):
    user_uid: str
    user_name: str
    section_instructors: str
    cells: dict[str, int]            # {question_no: 0|1}
    possible_points: int
    correct_answers: int
    score_pct: float

class QuestionSummaryStandard(BaseModel):
    cpalms_standard: str
    question_nos: list[str]          # ordered as displayed
    avg_score_pct: float             # for §2C header coloring

class QuestionSummaryGrandTotal(BaseModel):
    possible_points: int             # = num_students × max_possible_per_student
    correct_answers: int
    score_pct: float
    per_question: dict[str, dict]    # {q_no: {possible, correct, pct}}

class QuestionSummaryTeacher(BaseModel):
    section_instructors: str
    students: list[QuestionSummaryRow]
    subtotal: QuestionSummaryGrandTotal   # for §2B subtotal rows

class QuestionSummaryPayload(BaseModel):
    school: YTDSchoolInfo            # reuse existing
    assessment: AssessmentMeta       # item_name, subject, grade, session, assessment_type
    standards: list[QuestionSummaryStandard]
    teachers: list[QuestionSummaryTeacher]
    grand_total: QuestionSummaryGrandTotal
    kpis: QuestionSummaryKpis        # total_questions, total_students, score, possible_points, pct_correct
```

### SB.5 Backend endpoint

```python
# backend/app/api/v1/reports.py
@router.get("/question-summary",
            response_model=QuestionSummaryPayload,
            dependencies=[Depends(require_permission("reports:read"))])
async def question_summary(
    item_id: str,
    db: AsyncSession = Depends(get_db_with_rls),
) -> QuestionSummaryPayload:
    """Question-by-student matrix for one assessment.
    Mirrors PBIX ord 6/7/16 (RDL-backed Question Summary Report).
    Variants are pure UI; same payload feeds all three."""
    return await ReportService(db).build_question_summary(item_id=item_id)
```

### SB.6 Repository SQL — the core matrix

The RDL behind these three pages reads from `cube_users_summary`, which in
our model corresponds to `fact_student_submission` JOINed against
`cube_question_summary_overall` and `dim_item`. The minimal query
(replacing the legacy `cube_users_summary` view):

```sql
WITH submissions AS (
    SELECT
        f.user_uid,
        f.user_name,
        f.section_instructors,
        f.question_id,
        qso.question_no,
        qso.standards         AS cpalms_standard,
        CAST(f.points_received AS NUMERIC) AS points_received,
        CAST(f.points_possible AS NUMERIC) AS points_possible
    FROM fact_student_submission f
    JOIN cube_question_summary_overall qso
      ON qso.question_id = f.question_id
     AND qso.item_id     = f.item_id
    WHERE f.item_id = :item_id
)
SELECT
    user_uid, user_name, section_instructors,
    question_no, cpalms_standard,
    SUM(points_received)::NUMERIC / NULLIF(SUM(points_possible), 0) AS cell_pct,
    SUM(points_possible) AS poss, SUM(points_received) AS got
FROM submissions
GROUP BY user_uid, user_name, section_instructors, question_no, cpalms_standard;
```

Aggregate downstream in Python:
- Per-student row totals (`possible_points`, `correct_answers`, `score_pct`).
- Per-teacher subtotals (sum per `section_instructors`).
- Per-question grand totals (sum per `question_no`).
- Per-standard `avg_score_pct` (mean of `cell_pct` per `cpalms_standard`).

> **Cell value rule:** the PDF shows binary 0/1 cells for single-select MCQ
> but the underlying data has fractional `points_received / points_possible`
> for multi-select / partial credit. The legacy RDL renders the **integer
> floor** for display but presumably reverts to the fractional value for
> the Score % calc. For our rebuild, render `cell.score_pct == 1.0 ? 1 : 0`
> in the cell but use the fractional `cell.score_pct` for all aggregates.
> This matches the bug-fix policy in `docs/audit/fixes/01_q12_multiselect_applied.md`.

### SB.7 Color palette

Use existing tokens from `frontend/src/lib/reports/colors.ts`:

| Token            | Value     | Use                                              |
|------------------|-----------|--------------------------------------------------|
| `PERF_GREEN`     | `#00FF06` | correct cell, Score % ≥ 80%, §2C standard header ≥ 80% |
| `PERF_YELLOW`    | `Yellow` / `#FFFF00` | Score % 70-80%, §2C standard header 70-80% |
| `PERF_PINK`      | `#FFCCFF` | incorrect cell, Score % < 70%, §2C standard header < 70% |
| `INCORRECT_GREY` | `#CCCCCC` | (unused on these three variants — but available) |
| `HEADER_BAR_BG`  | `#B8DBFF` | Standard-code header in §2A / §2B (solid navy variant — pick a token or add `STANDARD_HEADER_NAVY = '#4472C4'`) |
| `LAYOUT_BORDER`  | `#B3B3B3` | tablix cell borders                              |
| `KPI_CARD_BG`    | `#B8DBFF` | (unused here — no KPI strip on shell)            |

Add one new token if not present:
```ts
export const QSR_HEADER_NAVY = '#4472C4';      // Office accent 1
export const QSR_HEADER_NAVY_LIGHT = '#8FAADC'; // Office accent 1 darker -0.25
```

---

## §3 Architectural notes & quirks

### 3.1 Why the actual report logic is invisible to PBIX

These pages embed a **Power BI Paginated (RDL) report** via `rdlVisual`.
The `.rdl` definition (XML defining the tablix, conditional fills, row
groups) lives on the Power BI Service workspace, not in the PBIX file we
extracted. `_extract.py` cannot reach it. Everything south of §1 (the
tablix spec) is therefore reverse-engineered from the rendered PDFs.

### 3.2 Why the data source is `cube_users_summary` but it's not in the model

`cube_users_summary` is referenced ONLY by the redacted Question Summary
Report (ord 17) and the redacted Question Response Analysis (ord 18) — see
`_layout.full.json:1483`. The non-redacted Question Summary variants do
not declare `cube_users_summary` in their PBIX projections; they just pass
six dimensional filter parameters via `parameterMapping`. The external
RDL re-binds those parameters to its own dataset, which on the PBI Service
hits `cube_users_summary` directly (a per-(user, question, item) fact view
that lives ONLY in the workspace dataset, not in this PBIX).

For our rebuild we replace `cube_users_summary` with a direct JOIN of
`fact_student_submission` × `cube_question_summary_overall` × `dim_item`
(see §SB.6).

### 3.3 The "Key Measures" / "Student Submissions" tables don't exist locally

The hidden multiRowCard (#4) references `Key Measures.Total Questions` etc.
But `02_tables.json` lists no `Key Measures` or `Student Submissions` table —
the model has `Measure`, `cube_question_summary_overall`, `fact_student_submission`,
etc. This is because the `Key Measures` table label is a **display-folder
rename** applied at the workspace level; in the storage model these
measures live on the `Measure` table and the `Student Submissions` data on
`fact_student_submission`. Same fields, different display label.

For implementation: ignore the labels, map directly to the five DAX
measures in §1.3.

### 3.4 Why three variants if they're so similar?

The PBIX-author shipped three rather than one because Power BI Paginated
Reports don't support runtime visual-config flags. Each variant needs its
own `.rdl` (own conditional-fill config, own subtotal-row config) — hence
three files on the workspace and three shell pages. **In our rebuild we
collapse them into one React component with two boolean props** (`colorHeaders`,
`teacherSubtotals`) — exactly what Power BI couldn't do.

### 3.5 What about `Question Summary Report redacted` (ord 17)?

Same shape, but rebinds the six parameters to `cube_users_summary` columns
directly (no `dim_*` indirection) and lives in a different workspace
(`cc11f76e-bf13-4c9c-a5f9-a1adaa9d5a0f`). The redaction replaces
`User_Name` with a hashed/anonymized label. Out of scope for this spec
(user asked for ord 6, 7, 16 only), but trivial to add as a fourth
variant flag: `<QuestionSummaryReport redacted />` mutates
`row.user_name → hash(row.user_uid)`.

### 3.6 Sort-order semantics — verifying against the PDF

The PDF shows students sorted ASC by Score % WITHIN each teacher group.
That ordering must come from the RDL tablix's `<SortExpressions>` on the
detail row group. Implement in React as:

```typescript
teachers.forEach(t =>
  t.students.sort((a, b) => a.score_pct - b.score_pct)
);
```

The teacher groups themselves appear alphabetical by `section_instructors`
(Elizabeth Sedlak → Mason Reeder → Taylor Almendinger on PDF page 1 of
the base sample).

---

## §4 Cross-references

| What                                                | Where                                                                                                                            |
|-----------------------------------------------------|----------------------------------------------------------------------------------------------------------------------------------|
| Page objects (full JSON)                            | `data/_pbix_extract/_layout.full.json:527-619` (ord 6), `:621-714` (ord 7), `:1291-1392` (ord 16)                                |
| Page list (text summary)                            | `data/_pbix_extract/20_pages.md:128-180` (ord 6, 7), `:345-371` (ord 16)                                                          |
| Fields per page                                     | `data/_pbix_extract/22_fields_per_page.json:115-176` (ord 6), `:178-241` (ord 7), and the matching block for ord 16                |
| DAX measures (cited inline above)                   | `data/_pbix_extract/04_dax_measures.dax` — `Total Student:134`, `Total Question:148`, `Grade_Average_Standard_Measure:215`, `Performance Color Standard:250`, `H2 - Assessment Type:320`, `H2 - Course and Unit:340`, `Total Possible Point:461`, `% Correct Answer:475`, `Score:482`, `H1 - Longitudinal:656` |
| Tables universe                                     | `data/_pbix_extract/02_tables.json`                                                                                              |
| Schema (cube_question_summary)                      | `data/_pbix_extract/03_schema.csv:30-69`                                                                                          |
| Schema (fact_student_submission)                    | `data/_pbix_extract/03_schema.csv:188-222`                                                                                       |
| Power Query M (SchoolID, SchoolLogo_Parameter)      | `data/_pbix_extract/07_power_query.m`                                                                                            |
| Sample rendered PDF — base                          | `data/sample reports/Paginated - Question Summary Report (1).pdf`                                                                |
| Sample rendered PDF — teacher subtotal              | `data/sample reports/Paginated - Question Summary Report - Teacher.pdf`                                                          |
| Sample rendered PDF — header highlights             | `data/sample reports/Paginated - Question Summary Report - color.pdf`                                                            |
| Extracted PDF text (working notes)                  | `.planning/reports-expansion/qsr-notes/qsr_base.txt`, `qsr_teacher.txt`, `qsr_color.txt`                                          |
| Reference spec at matching depth                    | `data/_pbix_extract/55_standard_summary_spec.md`                                                                                  |
| Sister-page Question Response Analysis spec         | `data/_pbix_extract/51_qra_spec.md` (uses the same `cube_users_summary` parameter pattern)                                       |
| Cube wiring / repository to extend                  | `backend/app/repositories/cube_repository.py`                                                                                    |
| Service layer to extend                             | `backend/app/services/report_service.py`                                                                                          |
| Existing report-shell components to reuse           | `frontend/src/components/app/modules/reports/shared/ReportCanvas.tsx`, `ReportPageHeader.tsx`, `AssessmentReportHeader.tsx`, `LoadingState.tsx`, `ErrorState.tsx` |
| Color palette                                        | `frontend/src/lib/reports/colors.ts`                                                                                              |
| Cube measure semantics doc                          | `docs/audit/06_cubes_and_reports.md:19` (`Grade_Average_Standard_Measure`)                                                       |
| Multi-select / Q12 fix policy                       | `docs/audit/fixes/01_q12_multiselect_applied.md`                                                                                  |

---

*Generated 2026-05-25 from `data/Assessment Analysis Dashboard.pbix` extracts
and rendered PDF samples. The tablix structure was reverse-engineered from
the rendered output because the external RDL definition is not in the PBIX
file. Re-run `_extract.py` to refresh source files; refresh PDFs from the
Power BI workspace if the RDL changes.*
