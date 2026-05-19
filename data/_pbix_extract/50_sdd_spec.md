# Standards Deep Dive Interactive — Implementation Spec

> **Scope:** PBIX page #16 *"Standards Deep Dive interactive"* in
> `data/Assessment Analysis Dashboard.pbix`. Source-of-truth files cited inline.
>
> **Audience:** an implementer building the Next.js + Recharts replica. This spec
> is exhaustive enough to rebuild without re-opening the PBIX.

---

## §1 Page-level metadata

- **Layout JSON path:** `_layout.full.json` lines 2358–2753 (page object).
  - `id: 282753170`, internal `name: "be4decefb52ed52d820d"`, `displayName: "Standards Deep Dive interactive"`, `ordinal: 1`.
- **Canvas:** `1280 × 720` (`width`/`height` lines 2746–2747).
- **Page background:** `outspace.color = #CACEDA` (light slate), set in page `config` line 2748.
- **Visual containers:** 39 (matches REPORT.md §7.2). Of those, ~10 are hidden scaffolding (`display.mode = "hidden"` or are children of a hidden `singleVisualGroup`); ~29 actually render.
- **Page-level filters** (line 2745, three of them, all `howCreated:5` = "filter pane categorical"):
  1. `dim_item.Item_Name` IN `["Module Assessment: My Community Heroes"]` — **saved filter value baked into the PBIX**. This is the assessment that was last selected when the file was saved; it scopes the entire page to ONE assessment (single Item_ID).
  2. `dim_strand.Strand` (Categorical, no Values list yet) — empty cross-filter slot. Populated when user clicks the Strand treemap.
  3. `dim_standard.cPalms_Standard` (Categorical, no Values list) — empty cross-filter slot. Populated when user clicks any per-standard chart.
- **No `slicer` visualType anywhere on the page.** Filtering is done via (a) the static page filter pane (Item_Name) and (b) cross-filter when the user clicks bars/treemap tiles.

> **Implication for our scoping question (§7 below):**
> The page is **per-assessment** (single Item via the page filter). Within that
> assessment, every visual aggregates across all sections / instructors. The
> "Strand" / "cPalms_Standard" page filters become non-empty only as a result of
> *interaction* (cross-filter), not via a slicer the user can see.

---

## §2 Slicers

**There are zero traditional slicer visuals on this page.**

The "slicer-like" UX is provided by:
- **Filter pane** (right edge, native PBI chrome): shows the three page-level
  filters listed in §1. The PBIX shipped with `dim_item.Item_Name = "Module
  Assessment: My Community Heroes"` baked in. To switch assessments the consumer
  edits this filter in the right pane.
- **Cross-filter via clicks** on the strand treemap (#11) and the per-standard
  charts (#27/#32/#34/#36). Power BI's default cross-highlight is implicit.
- **Two action buttons** (#6 "Back to Home", #8 nav stub) and one hidden
  "Reset" button (#12) — see §4.

Our rebuild must therefore expose:
- A **slicer panel** for `subject_id`, `assessment_id`, `section_id`,
  `instructor` (the Athenian rebuild *adds* this since the original was a
  per-school PBIX clone; we need this in one app).
- An **assessment selector** (replaces the baked-in `Item_Name` filter).
- **Click-through cross-filtering** between treemap, bars and the charticulator
  panels — each click sets/unsets a `strand` or `cPalmsStandard` filter on the
  page state.

---

## §3 KPI strip (top row, y ≈ 100)

Five cards across the top of the page, with a sixth "Instructor(s):" card
below them on the left. All cards share the same theme: title fontSize 14D,
value fontSize 20D bold, fill `#A0D1FF` (sky blue), border `#41a4ff` (radius
10D), divider line. Coordinates from `_layout.full.json` lines 2756–2826.

| # | Title | Position (x, y, w, h) | Measure (DAX) | Source measure |
|---|-------|---|---|---|
| #4 | **Total Students** | 17.87, 98.78, 291.1×71.46 | `Measure.Total Student` | `SUMX(SUMMARIZE(cube_school_summary, Item_ID, "x", MAX(Total_Students)), [x])` |
| #3 | **Number of Questions** | 335, 99.84, 291×71.46 | `Measure.Total Question` | `DISTINCTCOUNT(cube_question_summary_overall[Question_No])` |
| #2 | **Number of Standards** | 655, 99.84, 291.1×71.46 | `Measure.Total Standard` | `DISTINCTCOUNT(cube_question_summary_overall[Standards])` |
| #1 | **Grade Average** | 972, 99.84, 291.1×71.46 | `Measure.Grade_Average_Standard_Measure` | `AVERAGE(cube_question_summary_overall[Grade_Average])` (formatted `0.0%`) |
| #0 | **Instructor(s):** | 18.92, 201.77, 344.7×141.87 | `Titles.Instructor(s):` | `CONCATENATEX(DISTINCT(dim_Item[Section_Instructors]), ..., UNICHAR(10))` — newline-separated |

> **Note: no "Overall Lowest %" / "Overall Highest %" cards on the visible
> SDD page.** They exist (visuals #15, #16) but live inside a hidden group
> (`Group 1` / `da6d5ecab89312157de5`, `isHidden:true`, `_layout.full.json`
> line 2508). They were the dev's earlier draft, replaced by the four-card row
> above. Our rebuild can omit them on this page (they belong on Question
> Response Analysis Interactive — see REPORT.md §7.1).

**Header row (y ≈ 0–95):**
- #5 `simpleImage` of `SchoolLogo_Parameter.SchoolLogo_Parameter` (school logo) at (27.74, 17.46, 76×72).
- #6 actionButton "Back" → navigates to section `00d67f5030ed90a482a8` (Home page) at (21, 20, 82×73). Transparent over the logo.
- #7 textbox "Standards Deep Dive" at (120, 11, 450×22), fontSize ~24D bold dark gray. The page H1.
- #8 actionButton (no defined target — placeholder) at (21.68, 20.53, 82×73) — overlaps #6, likely a visual artifact.
- #37 multiRowCard `Titles.H2 - Course and Unit` at (121, 34, 728×31). Renders e.g. "Course: Grade 5: Math Module 3".
- #38 multiRowCard `Titles.H2 - Assessment Type` at (121, 57, 331×33). E.g. "Module Assessment".

---

## §4 Visual-by-visual catalogue

Coordinates and z-order from `_layout.full.json`. Annotations: **(VISIBLE)** =
renders at runtime; **(HIDDEN)** = `display.mode:"hidden"` or in a hidden
`singleVisualGroup` (selection-pane eye toggled off).

### 4.1 Header band (y < 95)

| # | Type | Title / Field | Pos (x,y,w,h) | Hidden? | Notes |
|---|------|----------------|---|---|---|
| #5 | simpleImage | SchoolLogo image | 27.7, 17.5, 76×72 | (V) | binds `SchoolLogo_Parameter.SchoolLogo_Parameter` |
| #6 | actionButton | Back → Home | 21, 20, 82×73 | (V) | `visualLink.type='Back'`, navigationSection `00d67f5030ed90a482a8` |
| #7 | textbox | "Standards Deep Dive" | 120, 11, 450×22 | (V) | static title |
| #8 | actionButton | (no target) | 21.7, 20.5, 82×73 | (V) | overlay |
| #37 | multiRowCard | `Titles.H2 - Course and Unit` | 121, 34, 728×31 | (V) | concat Grade + Item_Name |
| #38 | multiRowCard | `Titles.H2 - Assessment Type` | 121, 57, 331×33 | (V) | trimmed Assessment_type |
| #12 | actionButton | reset (icon=`reset`) | 1238, 55, 42×39 | (H) | `display.mode:"hidden"` — bookmark `Bookmarkfd28db145cb2f08c3dc5` |

### 4.2 KPI strip (y ≈ 95–175)

See §3. Five cards (#0…#4).

### 4.3 Strand treemap "# of Standards by Strand" — visual #11 **(VISIBLE)**

- **Type:** `treemap` at `(806, 198, 465×177)`, z=1000.
- **Title:** literal text `"# of Standards by Strand"` (in `vcObjects.title` but
  `show:false` — title is hidden in this build).
- **Group (category):** `dim_standard.Strand`.
- **Values (size):** `Measure.Total Question Strand`
  - DAX: `MAXX(ADDCOLUMNS(VALUES(dim_standard[Strand]), "x", CALCULATE(DISTINCTCOUNT(cube_question_summary_overall[Question_No]))), [x])` — i.e. **# of distinct question_no per strand**.
- **Tile fill:**
  - Default rule (`dataPoint.fill`, line 2478, third entry):
    `solid.color = expr.Measure { Property:"Performance Color Strand" }`.
  - Selector: `data.dataViewWildcard.matchingOption=1` (per-row).
  - **`Performance Color Strand` DAX (lines 181–197):**
    ```
    VAR High = 0.8, Low = 0.7
    VAR x = Measure[Grade_Average_Standard_Measure]
    SWITCH(TRUE(),
      x >= 0.8 → "#00FF06" (green),
      x < 0.7 AND x > 0 → "#FFCCFF" (pink),
      x > 0.7 AND x < 0.8 → "Yellow")
    ```
  - The two earlier entries are theme fallbacks (ColorId 5, ColorId 4) used
    only when the metadata selector matches `Key Measures.% of Correct Answers` /
    `% of incorrect answer` (ghost refs — never matches).
- **Layout:** `tilingMethod = "binary"`.
- **Visual-level filters** (line 2479):
  - `dim_strand.Strand` Categorical (open) — listens for cross-filter.
  - `cube_standard_summary.Strand_ID IS NOT NULL` (advanced filter — drop unmapped rows).
  - Two `cube_school_summary.Total_Questions` SUM filters (advanced, `howCreated:1` — auto-generated, prevent zero rows).
  - `Measure.Total Question Strand` and `Measure.Total Question Standard` advanced filters.
- **Cross-filter target:** clicking a tile sets `dim_strand.Strand` / `dim_standard.Strand` on the page → all other visuals filter.

### 4.4 Three side-by-side 100% Stacked Bar Charts ("Correct and Incorrect % by Standards")

This is the centrepiece of the page. **Three** bars, one per traffic-light
band, side by side at y≈416. Each is wrapped in a `singleVisualGroup`
container with a header bar (basicShape + textbox).

| # (group/inner) | Pos (x,y,w,h) | Group "Performance Band" | Correct color | Incorrect color |
|---|---|---|---|---|
| #26 / #27 | 385, 416, 280×291 | **green** (≥80%) | `#00FF06` | `#CCCCCC` |
| #31 / #32 | 676, 416, 285×291 | **yellow** (70%–79%) | `#FFFF00` | `#CCCCCC` |
| #33 / #34 | 969, 416, 280×291 | **pink** (<70%) | `#FFCCFF` | `#CCCCCC` |

All three share identical configuration EXCEPT the Correct color (`#00FF06`,
`#FFFF00`, `#FFCCFF`) and one extra advanced filter on `#34` that includes
the `cube_standard_summary.Strand_ID IS NOT NULL` constraint.

- **Type:** `hundredPercentStackedBarChart`.
- **Y-series (legend):**
  1. `Measure.Grade_Average_Standard_Measure` (= AVG `Grade_Average`).
  2. `Measure.Incorrect_Grade_Average_Standard_Measure` (= 1 − above).
- **Category (Y-axis):** `dim_standard.cPalms_Standard` (one bar per standard).
- **Tooltip:** `Sum(cube_standard_summary.Total_Questions)`.
- **Selector-based color rules** (the literal hex per band is the same for
  every standard in that band — it's NOT a per-row conditional format):
  ```
  dataPoint, selector.metadata = "Measure.Grade_Average_Standard_Measure" → green | yellow | pink
  dataPoint, selector.metadata = "Measure.Incorrect_Grade_Average_Standard_Measure" → #CCCCCC
  ```
- **Visual-level filter (the band selector):** each chart has an Advanced
  filter on `Measure.Grade_Average_Standard_Measure`:
  - Green chart (#27): `value >= 0.8`
  - Yellow chart (#32): `value >= 0.7 AND value < 0.8`
  - Pink chart (#34): `value < 0.7`
  - Plus shared categorical filter on `dim_standard.cPalms_Standard`
    (cross-filter slot) and `Total_Questions IS NOT NULL`.
- **Group header (the basic-shape + textbox above each band):**
  - Group 2 (`a8d2ce8788ebecc45609`, visible) at (376, 171, 900×31.6) —
    horizontal divider band that spans the page width above the *strand*
    charticulator (#35). The textbox holds the H2 label "Strand
    Performance" or similar.
  - Group 2 (`0099551075094e5e0e30`, visible) at (376, 380, 900×35.5) —
    horizontal divider band above the three 100% bars.

### 4.5 Charticulator visuals (the per-row "tables")

Two custom `charticulatorVisualCommunity_VIEW` instances. These are the page's
"data tables" — they look table-like but are rendered as Charticulator
templates. Each row is one Strand or one cPalms_Standard with an inline pill
showing pct + count, color-coded by Performance Color.

#### #35 — Per-Strand row strip **(VISIBLE)**
- **Pos:** (384.26, 199.2, 421.5×176) — overlaps the right-side strand treemap area.
- **Primary key (row group):** `dim_standard.Strand`.
- **Fields used by the Charticulator template:**
  - `Measure.Total Standard` (count of standards in the strand).
  - `Measure.Total Question Strand` (count of questions).
  - `Measure.Grade_Average_Standard_Measure` (avg %).
  - `Measure.Performance Color Strand` (text label → hex code, used as row fill).
- **Filters:** four advanced auto-filters dropping null Strand_ID and zero rows.
- **Rebuild:** simple HTML/Tailwind table grouped by `strand`, columns
  `# Standards | # Questions | Grade Average %`, row background = Performance Color (green / yellow / pink) based on Grade_Average.

#### #36 — Per-Standard row strip **(VISIBLE)**
- **Pos:** (11.35, 359.41, 358×346) — bottom-left quadrant.
- **Primary key:** `dim_standard.cPalms_Standard` (one row per standard, e.g. "MA.5.NBT.2").
- **Links field:** `dim_standard.cPalms_Standard` (used by Charticulator to link to drill-through page).
- **Fields:**
  - `Measure.Total Standard` (= 1 per row, shown as a count badge).
  - `Measure.Total Question Standard` (count of questions tagged to that standard).
  - `Measure.Grade_Average_Standard_Measure` (% correct).
  - `Measure.Performance Color Standard2` (= same SWITCH as Strand, but on
    cube_question_summary_overall.Grade_Average; lines 1043–1056). The "2"
    suffix has no functional difference.
- **Filters:** three advanced auto-filters; `cPalms_Standard` cross-filter slot.
- **Rebuild:** scrolling list/table of standards within the (filtered) strand;
  each row = `[cPalms code]  ███████ X questions   65.4%`. Pill fill from
  Performance Color (red/pink at <70%, yellow 70–80%, green ≥80%).

### 4.6 Hidden scaffolding (DON'T port these)

| # | Type | Why hidden | Notes |
|---|------|-----------|-------|
| #9 | funnel "Standards by # of Questions" (391.96, 127.64, 444×592) | `display.mode:"hidden"` | uses ghost refs `Standards.Standard`, `Key Measures.*` |
| #10 | treemap (704, 127, 569×201) | `display.mode:"hidden"` | ghost refs |
| #12 | actionButton "reset" (1238, 55, 42×39) | `display.mode:"hidden"` | bookmark `Bookmarkfd28db145cb2f08c3dc5` |
| #13 | tableEx (811.42, 98, 469×235) | `display.mode:"hidden"` | ghost refs `Standards.Schoology Short Standard`, `Key Measures.*`. Backcolor expression *would* use `Performance Color Standard` (line 2498) but the visual never renders. |
| #14 | singleVisualGroup `Group 1` (286.55, 127, 136×202) | `isHidden:true` (selection-pane) | wraps #15 (Overall Lowest) & #16 (Overall Highest) |
| #20 | singleVisualGroup `100% Stack 2` (723, 127, 550×201) | `isHidden:true` | wraps #21 barChart + #22 clusteredBarChart variants — earlier draft of the 3-band 100%-stack |
| #23 | singleVisualGroup `Group 3` (5.69, 317, 327×391) | `isHidden:true` | wraps #24 funnel + #25 clustered bar (sub-standard count) |

These are **legacy template scaffolding** the original author hid but didn't
delete. None should be re-implemented in our rebuild.

---

## §5 Scoping & interaction

### Per-row vs per-page filtering

**Resolved:** the page is **per-assessment (per-Item) only**, with the
assessment selected via the page filter pane. *Within* that assessment:

- KPI cards (#0–#4) aggregate across all sections / questions / students of
  the selected assessment.
- Treemap #11 groups by `dim_standard.Strand` — all strands in the selected
  Item's questions, sized by `Total Question Strand`.
- 100%-stacked bars #27/#32/#34 group by `dim_standard.cPalms_Standard`,
  filtered to standards whose Grade_Average is in their respective traffic-
  light band.
- Charticulator #35 → one row per Strand. Charticulator #36 → one row per
  cPalms_Standard.

**There is NO per-section or per-instructor breakdown on this page.** The
PBIX has separate pages "Question Response Analysis by Teacher" / "by
Standard and Teacher" for that.

### Cross-filter chain

```
User clicks ─────► strand treemap (#11)
                        │ sets dim_strand.Strand = X
                        ▼
       all other visuals filter to standards in that strand
                        │
User clicks ─────► per-standard chart (#27/32/34/36)
                        │ sets dim_standard.cPalms_Standard = Y
                        ▼
       cube_standard_summary aggregates collapse to one row
```

### Buttons / drill-through targets

- **#6 "Back" actionButton** → page navigation to section `00d67f5030ed90a482a8` (Home).
- **#8 actionButton** → no target (default visualLink only).
- **#12 hidden Reset button** → bookmark `Bookmarkfd28db145cb2f08c3dc5` (clears all cross-filters; not exposed in this build).

There is **no page-level drill-through** *out of* SDD. Drill-through *into*
the "Incorrect Answer Details" page (#20) is implemented from the Question
Response Analysis pages, not from SDD.

---

## §6 Color thresholds reference

The SDD page uses the project-wide **70% / 80% three-band** convention.

```
< 70%       →  PINK    "#FFCCFF"   ← under-performing
70%–80%     →  YELLOW  literal name "Yellow" or "#FFFF00"
≥ 80%       →  GREEN   "#00FF06"   ← target
incorrect   →  GREY    "#CCCCCC"
```

Defined in DAX:
- `Performance Color Strand` (lines 181–197 of `04_dax_measures.dax`) — uses `Measure.Grade_Average_Standard_Measure` as input.
- `Performance Color Standard2` (lines 1043–1056) — same logic, same input. The duplicate exists only because Power BI doesn't allow re-using one measure as conditional fmt source for two different visuals.

> **Edge cases in the DAX (worth replicating exactly):**
> - The pink branch is `x < Low AND x > 0` — **a value of exactly 0 is uncolored** (PBIX renders default theme color, which is grey).
> - The yellow branch is `x > Low AND x < High` (strict on both sides). At
>   exactly 0.7 the value falls into NO branch on `Performance Color Strand`
>   (gap in the SWITCH); at exactly 0.8 it falls into the green branch. The
>   `Performance Color Standard2` variant uses `>= Low` so 0.7 hits yellow.
>   Replicate by treating `[Low, High)` → yellow, `>= High` → green, `< Low` → pink.

The treemap #11 fill: per-tile, evaluated via `Performance Color Strand`. So a
strand with average ≥ 80% is green, 70–80% yellow, <70% pink. (Tile *size* is
`Total Question Strand`.)

The 100%-stacked bars #27/#32/#34 use a fixed color per chart (because each
chart is filtered to one band).

---

## §7 The "per-strand vs per-pair" row-grouping question (RESOLVED)

> **Question from the brief:** "When the table shows 'Algebraic Reasoning'
> with 1 standard / 1 question / 51.9% — is that ONE row per (strand,
> identifier) pair, or ONE row per strand collapsed?"

**Answer:** the SDD page does NOT show a (strand, identifier) pair table.
There are two separate visuals:

1. **Charticulator #35** = one row per **Strand** (e.g. "Algebraic
   Reasoning"), with `Total Standard` (count of distinct cPalms_Standards in
   that strand), `Total Question Strand` (count of distinct question_no), and
   `Grade_Average_Standard_Measure` (average over all rows in the strand).
   *Strand-level rollup, fully collapsed.*

2. **Charticulator #36** = one row per **cPalms_Standard** (e.g.
   "MA.5.AR.1.1"), with `Total Question Standard` (count of question_no for
   that one standard) and `Grade_Average_Standard_Measure` (average over
   that one standard's rows). *Standard-level, ONE row per cPalms_Standard.*

Neither is "per (strand, identifier) pair" — that grain only exists in
`cube_standard_summary` itself (one physical row per `Item_ID × Identifier`),
but every visual on this page aggregates it.

**Our current implementation bug:** if our table is showing duplicates for
"Algebraic Reasoning" (e.g. one row of "Algebraic Reasoning / 1 standard / 1
question / 51.9%" repeating per identifier), we're rendering the raw
`cube_standard_summary` rows without the SUMMARIZE/aggregation step. The
fix is to:

- For the Strand-level view: `GROUP BY strand`, `COUNT(DISTINCT identifier)`,
  `COUNT(DISTINCT question_no)`, `AVG(grade_average)` — this matches DAX's
  `Total Standard`, `Total Question Strand`, `Grade_Average_Standard_Measure`.
- For the cPalms_Standard-level view: `GROUP BY cPalms_Standard`,
  `COUNT(DISTINCT question_no)`, `AVG(grade_average)`.

In both cases we're averaging `cube_question_summary_overall.Grade_Average`
(NOT `cube_standard_summary.Grade_Average`) — that's the
`Grade_Average_Standard_Measure` definition (line 243).

> **Pitfall:** `Measure.Total Question Strand` (line 419) is NOT a sum — it's
> `MAXX(ADDCOLUMNS(VALUES(dim_standard[Strand]), "x",
> CALCULATE(DISTINCTCOUNT(cube_question_summary_overall[Question_No]))), [x])`.
> When the report shows 1 strand selected the visible value is just
> `DISTINCTCOUNT(question_no)`. When multiple strands are selected, it's the
> MAX across strands of that distinct count — useful as a chart-axis cap, NOT
> a sum. **Replicate the MAXX behaviour exactly** if we want our totals to
> match the PBIX visuals.

---

## §8 Implementation notes for our rebuild

### Backend (FastAPI) — endpoints to add

```
GET /api/v1/reports/sdd/kpis?item_id=…       → 5-card values
GET /api/v1/reports/sdd/strands?item_id=…    → row per strand  (#35 + #11)
     [{ strand, n_standards, n_questions, grade_avg, perf_color }]
GET /api/v1/reports/sdd/standards?item_id=…&strand?  → row per cPalms_Standard
     [{ cpalms_standard, strand, n_questions, grade_avg, perf_color }]
GET /api/v1/reports/sdd/standards/by-band?item_id=…&band={green|yellow|pink}
     → for the three 100%-stack bars (filtered by band)
```

All endpoints must accept the implicit `school_id` (from auth claims) and the
required `item_id`. Optional cross-filter params: `strand`, `cpalms_standard`.

### Frontend (Next.js + shadcn + Recharts)

| PBIX visual | React component |
|---|---|
| KPI cards × 5 | `<KpiStrip>` (re-used from QRA page) — sky-blue card, 20D label |
| Treemap #11 | `<StrandTreemap>` — Recharts `<Treemap>`, `dataKey="n_questions"`, `<Cell fill={perfColor}>`. **Cross-filter on click → set strand state.** |
| 3 × 100%-stacked bar | `<PerformanceBandChart band="green|yellow|pink">` — Recharts horizontal stacked bar, fixed color per band, axis = `cPalms_Standard`, value = `[grade_avg, 1-grade_avg]`. Filter rows where band matches. |
| Charticulator #35 | `<StrandRowList>` — simple `<table>` of strands with pill background = perfColor |
| Charticulator #36 | `<StandardRowList>` — same, but per `cPalms_Standard` |
| H2 multiRowCards | `<PageSubHeader course={…} unit={…} assessmentType={…} />` |

### Color tokens (Tailwind extend)

```
'perf-green':   '#00FF06',
'perf-yellow':  '#FFFF00',
'perf-pink':    '#FFCCFF',
'perf-grey':    '#CCCCCC',
'header-blue':  '#A0D1FF',
'header-blue-border': '#41a4ff',
'page-bg':      '#CACEDA',
```

Use semantic Tailwind tokens via `globals.css` (per CLAUDE.md rule).

### Final canvas geometry (for pixel-perfect parity at 1280-px wide breakpoint)

```
Header:                   y=0…95   (logo, nav, title, course/assessment subtitles)
KPI strip:                y=95…175 (4 cards) + Instructor card y=175…340 (left col)
Strand treemap:           y=198…375 right side (806…1271)
Per-strand charticulator: y=199…375 middle (384…806)
Per-standard charticulator: y=359…705 left (11…370)
3 × 100%-stack bars:      y=416…707 right (385…1249)
Group 2 dividers:         y=171 and y=380 (full-width header bars)
```

Mobile responsive: stack vertically (KPI strip → strand treemap → per-strand
list → per-standard list → 3 band charts).

---

## §9 Cross-references

| What | Where |
|---|---|
| Page object & visual JSON | `_layout.full.json` lines 2358–2753 |
| Visual list (summary) | `20_pages.json` lines 3309–3899 |
| Per-page field map | `22_fields_per_page.json` lines 1157–1252 |
| DAX measures | `04_dax_measures.dax` (cited inline; `Performance Color Strand` line 181, `Total Question Strand` line 405, `Performance Color Standard2` line 1043, `Treemap Color` line 1075) |
| Power Query M | `07_power_query.m` (`dim_item` filter line 32, `dim_subject` line 53, `dim_strand` line 76) |
| Cube schema | `10_table_heads.json` lines 169–183 (`cube_standard_summary`) |
| Companion analysis | `REPORT.md` §7.2 lines 315–330 |

---

*Generated 2026-05-08. Re-run `_sdd_extract.py` (in this folder) to refresh
the visual-by-visual dump if the PBIX is rebuilt.*
