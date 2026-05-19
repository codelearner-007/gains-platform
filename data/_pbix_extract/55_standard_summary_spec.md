# Standard Summary — Implementation Spec

> **Scope:** PBIX page *"Standard Summary"* (`ordinal: 14`, internal section
> name `6f9c5b2041e0e8a0b71e`) in `data/Assessment Analysis Dashboard.pbix`.
> REPORT.md §6 lists it as Page 1 (the first page in display order),
> 23 visuals, working (paginated). Source-of-truth files cited inline.
>
> **Audience:** an implementer building the Next.js + Recharts replica at
> `frontend/src/app/app/reports/standard-summary/page.tsx`. This spec is
> exhaustive enough to rebuild without re-opening the PBIX.
>
> **Critical reading note before you start:** the original PBIX page is a
> **paginated PDF template** with a 320 × 240 canvas — i.e., a per-row repeating
> "card" rendered once per `(dim_subject, dim_standard)` combination, not a
> single school-wide dashboard. The user's brief asks us to **repurpose** that
> template into a single web page that shows the school-wide rollup as a list
> of these per-standard cards, plus a small KPI strip and the two summary bar
> charts duplicated globally. Do not literally recreate the 320 × 240 paginated
> render; instead, treat that 320 × 240 block as the design template for ONE
> CARD in our school-wide grid. See §1 and §9.

---

## §1 Page-level metadata

- **Layout JSON path:** `_layout.full.json` lines **5 – 243** (page object).
  - `id: 282753155`, internal `name: "6f9c5b2041e0e8a0b71e"`,
    `displayName: "Standard Summary"`, `ordinal: 14`,
    `objectId: "b15c00d7-2ede-42f1-a955-f51611f88483"`.
  - `displayOption: 3` (paginated render — fits to one logical "card" per
    row of the slicer set).
- **Canvas:** `320 × 240` (`width`/`height` lines 236–237). This is **1/4 the
  width and 1/3 the height** of the SDD interactive page (1280 × 720). The
  small canvas is the giveaway that this is a paginated/RDL template, not a
  free-form dashboard.
- **Page background:** none defined at page `config` (line 238 — only
  `{"visibility":1,"type":1}`). The PBIX renders the platform-default
  light grey.
- **Visual containers:** 23 (lines 6–233), broken down as:
  - 6 × `multiRowCard`
  - 5 × `card`
  - 4 × `basicShape` (decorative dividers + framing rectangles)
  - 2 × `textbox`
  - 1 × `barChart`
  - 1 × `clusteredBarChart`
  - 4 × `singleVisualGroup` containers (custom display-name groups; their
    `visualType` field appears as the synthetic group GUID
    `2ca6d33504829e750a95`, `e712919d449c265390ee`, `10c98baa69d0e9b906e0`,
    `8d6cc76fae14ecdc6090` in `20_pages.md`)
- **Page-level filters** (line 235): `"filters": "[]"` — **no page-level
  filters**. Unlike SDD which bakes in `dim_item.Item_Name = "Module
  Assessment: My Community Heroes"`, this page is filtered exclusively at
  the **M-parameter / `SchoolID` level** (see §2).
- **No `slicer` visualType anywhere on the page.** Filtering is done via
  Power BI's paginated-render context: each rendering of the template page
  receives ONE `(Subject, Strand, cPalms_Standard)` row from the
  Cartesian product of the bound dimensions.

> **Implication for our scoping question (§6 below):**
> The page is **per-(Subject × Standard)** in the original PBIX. Every visual
> binds to fields that resolve to a SINGLE row per render: e.g., the
> "Description" card uses `Min(dim_standard.Custom.CleanedDescription)`,
> the "Standard" multiRowCard uses `dim_standard.cPalms_Standard`, etc.
> Multiple standards become multiple PDF pages.
>
> For our rebuild we do not paginate; we replace the M-parameter-driven
> render loop with a React `.map()` that renders ONE card per row of the
> school-wide standards aggregation, plus a global KPI strip and the two
> shared bar charts at the top. This matches the user's brief
> ("school-wide standards rollup").

---

## §2 Slicers / filter-pane behaviour

**There are zero traditional slicer visuals on this page.**

The "slicer-like" UX in the original PBIX is provided by:
- **M-parameter scoping** — every cube/dim is filtered to one school via the
  `SchoolID` Power Query parameter (`07_power_query.m` lines 32–49 for
  `dim_item`; line 53–62 for `dim_subject`). Tenant isolation = clone the
  PBIX per school. There are **no DAX RLS roles** in this PBIX.
- **Filter-pane page filter** — empty in the saved file (line 235). Unlike
  SDD this page does not bake in an Item_Name filter; the paginated render
  iterates over all rows of the joined dimension.
- **Implicit pagination grain** — `dim_subject` × `dim_standard` produces
  one PDF page per combination, with the visuals binding to a single row.

Our rebuild must therefore expose:
- A **slicer panel** (re-using `<ReportFilters>` from
  `frontend/src/components/app/modules/reports/shared/ReportFilters.tsx`)
  with these filters: **session** (academic year), **subject**, **grade**.
  We deliberately **omit `category` and `section`** because the Standard
  Summary is school-wide and not bound to a single assessment. For
  symmetry with SDD/QRA the same `<ReportFilters>` component can be reused
  if we ignore the `category`/`section` selections in the request.
- An optional **strand sub-filter** (client-side cross-filter on the rendered
  card list) — see §5.
- The `school_id` is implicit from `app.current_school_id` GUC (RLS), same
  pattern as the existing reports (e.g., `cube_repository.py` lines 1–14).

---

## §3 KPI strip

The original PBIX page has **no dedicated KPI strip** (the canvas is too
small for one). Two text-only `multiRowCard`s along the top of the per-card
template stand in for KPIs:

| # | Title | Position (x, y, w, h) | Measure (DAX) | Formula source |
|---|-------|---|---|---|
| #0 | **# of standard** (label only) | 0.26, 80.43, 319.66×25 | `Titles.H3 - # of  questions` | `"Number of Questions: " & CALCULATE('Measure'[Total Question])` (DAX line 293) |
| (n/a) | (no other KPI cards on this page) | — | — | — |

The Strand Summary sister-page (ord 15) has TWO such cards — `H3 - # of
questions` AND `H3 - # of standards`. Standard Summary only has the
questions one, because the standards count for ONE standard is always 1.

> **Note on `Titles.H3 - # of  questions`** (the literal name has a
> double-space — `# of  questions` — preserved exactly in
> `04_dax_measures.dax` line 293):
> ```
> H3 - # of  questions =
>     "Number of Questions: " & CALCULATE('Measure'[Total Question])
> ```
> In a per-standard render, this resolves to "Number of Questions: N"
> where N = `DISTINCTCOUNT(cube_question_summary_overall[Question_No])`
> filtered to that standard.

**For our rebuild, we add a real KPI strip** at the top of the page since
we have the canvas room (we are not 320 × 240 paginated). Reuse the
existing `KpiStrip` shape from
`frontend/src/components/app/modules/reports/sdd/KpiStrip.tsx` minus the
"Instructor(s)" card (school-wide, no instructor scope), giving 4 cards:

| # | Title | Source measure (DAX) | Formula |
|---|-------|----------------------|---------|
| 1 | **Total Students** | `Measure.Total Student` (line 134) | `SUMX(SUMMARIZE(cube_school_summary, Item_ID, "x", MAX(Total_Students)), [x])` (school-wide sum across items) |
| 2 | **Number of Standards** | `Measure.Total Standard` (line 159) | `DISTINCTCOUNT(cube_question_summary_overall[Standards])` |
| 3 | **Number of Questions** | `Measure.Total Question` (line 148) | `DISTINCTCOUNT(cube_question_summary_overall[Question_No])` |
| 4 | **Grade Average** | `Measure.Grade_Average_Standard_Measure` (line 215) | `AVERAGE('cube_question_summary_overall'[Grade_Average])` (formatted `0.0%`) |

These four are the same DAX measures used by SDD's KPI strip (with the
"Instructor(s)" card removed). Reuse the existing
`backend/app/services/report_service.py::SddKpis` shape minus
`instructors`, or define a new `StandardSummaryKpis` schema (see §8).

---

## §4 Visual-by-visual catalogue

Coordinates and z-order from `_layout.full.json`. Annotations: **(VISIBLE)** =
renders at runtime; **(HIDDEN)** = `display.mode:"hidden"` or in a hidden
`singleVisualGroup`. References to `parentGroupName` link a child to one of
the four `singleVisualGroup` containers:
- `2ca6d33504829e750a95` ("Footer", visible) — bottom-of-card date row
- `e712919d449c265390ee` ("Subject & Grade", visible) — top-right tag row
- `10c98baa69d0e9b906e0` ("100% Stack 2", visible) — left bar-chart group
- `8d6cc76fae14ecdc6090` ("Top Subdetails", visible) — strand + cluster rows

**Indexing convention:** visual numbers below are the 0-indexed position of
each container in `_layout.full.json`'s `visualContainers` array (matching
the convention used by `_sdd_extract.py`). 23 containers total → indices
#0 … #22.

### 4.1 Top header row (y ≈ 0–27)

| # | id | Type | Title / Field | Pos (x,y,w,h) | Hidden? | Notes |
|---|---|------|----------------|---|---|---|
| #3 | 8695561684 | multiRowCard | `dim_standard.cPalms_Standard` | 0, 0, 320×27, z=5000 | (V) | The standard code, e.g., "MA.5.NBT.2". `vcObjects.background.color = '#0E1A77'` (deep navy), `cardTitle.fontSize=14D`, `cardTitle.color` from theme color 0 (white). **THE most prominent label.** |
| #8 (group) | 8695561689 | singleVisualGroup `e712919d449c265390ee` "Subject & Grade" | (header tag) | 168.85, 0, 151.15×26.95, z=6000 | (V) | Hosts visuals #11 (Subject), #12 (Grade), #9/#10 shapes. Right-side header tag. |
| #9 | 8695561690 | basicShape | rectangle (background frame) | 3.87, 5.16, 147.2×16.5 | (H) `display.mode:"hidden"` | parentGroup `e712919d449c265390ee`. Hidden white frame. |
| #10 | 8695561691 | basicShape | rectangle (vertical divider) | 126.02, 0, 12.18×26.95 | (V) | Theme color 3 darkened −0.5 (charcoal) — the small color tab between Subject and Grade. parentGroup `e712919d449c265390ee`. |
| #11 | 8695561692 | multiRowCard | `dim_subject.Subject` | 0, 2.32, 132.24×22.69 | (V) | The subject text (e.g., "Math"). parentGroup `e712919d449c265390ee`. fontSize 10D, color theme 8 darker 0.6. |
| #12 | 8695561693 | multiRowCard | `dim_subject.Grade_no` | 132.24, 2.3, 18.91×22.75 | (V) | Last char of grade ("5" for "Grade 5"). Calc col `dim_subject[Grade_no] = RIGHT([Grade], 1)` (DAX). parentGroup `e712919d449c265390ee`. |

### 4.2 Top sub-details (y ≈ 25.6 – 80.5) — group `8d6cc76fae14ecdc6090` "Top Subdetails"

| # | id | Type | Title / Field | Pos (x,y,w,h) | Hidden? | Notes |
|---|---|------|----------------|---|---|---|
| #16 (group) | 8695561697 | singleVisualGroup `8d6cc76fae14ecdc6090` "Top Subdetails" | — | 0, 25.56, 319.66×54.98, z=4000 | (V) | Hosts #17 line, #18 cluster card, #19 Strand card, #20 background, #21 line, #22 Cognitive_Complexity_Rating card. |
| #19 | 8695561700 | card | `Min(dim_standard.Strand)` (also as title text expr) | 4.86, 0, 302.11×19.42 | (V) | Strand label (e.g., "Number Sense and Operations"). The most informative line on the card. parentGroup `8d6cc76fae14ecdc6090`. |
| #18 | 8695561699 | card | bound to `dim_standard.blank`, title expr = `Min(dim_standard[cluster])` | 4.86, 18.4, 290.1×18.66 | (V) | Renders the cluster name (e.g., "Place Value with Whole Numbers"). parentGroup `8d6cc76fae14ecdc6090`. |
| #22 | 8695561703 | card | bound to `dim_standard.blank`, title expr = `Min(dim_standard[Cognitive_Complexity_Rating])` | 4.9, 36.42, 290.01×18.56 | (V) | Renders e.g. "Low" / "Moderate" / "High". parentGroup `8d6cc76fae14ecdc6090`. |
| #17 | 8695561698 | basicShape | line (90° rotation, weight 1, theme color 0 darker 0.5) | 0, 9.71, 300.83×18.66 | (V) | Visual divider between Strand and cluster rows. parentGroup `8d6cc76fae14ecdc6090`. |
| #21 | 8695561702 | basicShape | line (same style as #17) | 0, 28.17, 300.84×18.56 | (V) | Visual divider between cluster and Cognitive Complexity. parentGroup `8d6cc76fae14ecdc6090`. |
| #20 | 8695561701 | multiRowCard | `dim_standard.blank` (background only) | 0, 1.25, 319.66×53.62 | (V) | Background container; theme color 0 darker −0.3 fill (very light grey). parentGroup `8d6cc76fae14ecdc6090`. |

> **Important pattern:** several "card" visuals are bound to
> `dim_standard.blank` (a measure that returns empty) **purely as an
> anchor**, while the actual text shown comes from `vcObjects.title.text`
> being set to a column-aggregation expression (e.g.,
> `Aggregation(Function:3, Column: dim_standard.cluster)`). This is a PBI
> trick to render a column value as a card "title" rather than as the card
> "value". For our rebuild, just render the text directly in the React
> component — we don't need to reproduce the DAX trick.

### 4.3 KPI label row (y ≈ 80.5)

| # | id | Type | Title / Field | Pos (x,y,w,h) | Hidden? | Notes |
|---|---|------|----------------|---|---|---|
| #0 | 8695561681 | multiRowCard | `Titles.H3 - # of  questions` | 0.26, 80.43, 319.66×25 | (V) | Renders "Number of Questions: N" — the only KPI on this template. fontSize 12D. Border on (theme color 3 darker −0.25). |

### 4.4 Description block (y ≈ 84.5 – 218.5)

| # | id | Type | Title / Field | Pos (x,y,w,h) | Hidden? | Notes |
|---|---|------|----------------|---|---|---|
| #1 | 8695561682 | card | `Min(dim_standard.Custom.CleanedDescription)` | 0, 84.55, 320.17×134.05 | (V) | The HTML-stripped standard description. Source: `dim_standard.Custom.CleanedDescription` (M power query line 123 — `Html.Table([description], {{"CleanedDescription", ":root"}})` strips HTML). Word-wrap on. fontSize 12D. **The largest text block on the card.** |
| #2 | 8695561683 | textbox | "Description:" label | 0, 190.56, 66.88×27.96 | (H) `display.mode:"hidden"` | Static label "Description:" — hidden because the description block above is self-explanatory. |

### 4.5 Per-standard chart pair "Correct and Incorrect % by Standards" (y ≈ 61 – 121.5)

This is the centrepiece data viz on the per-standard card. **Two charts
overlaid in the same group**, one a `barChart` and one a `clusteredBarChart`,
both grouped inside `singleVisualGroup` `10c98baa69d0e9b906e0` ("100% Stack
2", visible). They live to the **right** of the description block, at the
top-right of the card.

| # | id | Type | Pos (x,y,w,h) | Hidden? |
|---|---|------|---|---|
| #13 (group) | 8695561694 | singleVisualGroup `10c98baa69d0e9b906e0` "100% Stack 2" | 168.89, 61, 150.89×60.51, z=7000 | (V) |
| #14 | 8695561695 | barChart | 0, 0, 150.89×60.51, z=1000 (relative to group) | (V) |
| #15 | 8695561696 | clusteredBarChart | 0, 0, 150.89×60.51, z=0 (relative to group) | (V) |

#### #14 — `barChart` (the % correct bar)

- **Y (value):** `Measure.Grade_Average_Standard_Measure`
  (DAX line 215: `AVERAGE(cube_question_summary_overall[Grade_Average])`).
- **Category (axis):** `dim_standard.cPalms_Standard` (one bar per standard
  in scope; in the per-card paginated context this is just one bar).
- **Order:** descending by `Grade_Average_Standard_Measure`.
- **Per-bar fill (selector `data.dataViewWildcard.matchingOption=1`):**
  inline conditional expression — **NOT the DAX `Performance Color`
  measure**, but a directly-embedded SWITCH:
  - `0 < grade < 0.7`  → `'#FFCCFF'` (pink)
  - `0.7 < grade < 0.8` → `'#faff00'` (yellow — note the slightly different
    yellow vs SDD's `'Yellow'` named color or `'#FFFF00'`)
  - `0.8 < grade < 2`   → `'#00ff06'` (green)
- **Default fallback fill** (selector `metadata="Key Measures.% of incorrect
  answer"`): theme color 0 darkened −0.3 — ghost selector, never matches.
- **Axes:** value axis hidden, end at 1D; category axis hidden;
  `concatenateLabels:true`, `labelOverflow:true`,
  `labelPosition:'InsideEnd'`, fontSize 8D, precision `1L`.
- **Title:** `'Correct and Incorrect % by Standards'` defined in
  `vcObjects.title.text` but `show:false`.
- **Tooltip:** binds `ReportSection9f325cd482d41bd17529` (a custom-tooltip
  page that doesn't exist in this PBIX → effectively no tooltip).
- **Visual-level filters:** none (`"filters": "[]"`).
- **parentGroupName:** `10c98baa69d0e9b906e0`.

#### #15 — `clusteredBarChart` (the % incorrect bar with question-count tooltip)

- **Y (value):** `Measure.Incorrect_Grade_Average_Standard_Measure`
  (DAX line 551: `1 - [Grade_Average_Standard_Measure]`).
- **Tooltip:** `Sum(cube_standard_summary.Total_Questions)` —
  this is how the question count surfaces on hover/tooltip.
- **Category (axis):** `dim_standard.cPalms_Standard`.
- **Order:** descending by `Incorrect_Grade_Average_Standard_Measure`.
- **Per-bar fill** (3 selectors, the third is the active one with
  `dataViewWildcard.matchingOption=1` but with empty `properties:{}`):
  bars render with the **theme default** since no conditional is set.
  In practice this means the incorrect-bar uses theme color 0 darker
  −0.3 (a soft grey).
- **Axes:** value axis hidden, end at 0.06D (very compressed!); category
  axis hidden.
- **Title:** `'Correct and Incorrect % by Standards'`, `show:false`.
- **parentGroupName:** `10c98baa69d0e9b906e0`.

> **What this dual-bar setup actually renders:** The PBIX overlays a green
> "% correct" bar (length proportional to grade_average) on top of a grey
> "% incorrect" bar. Because both axes have different ends (1D vs 0.06D)
> and only the correct bar carries the color rule, the visual reads as a
> single colored bar at ~`grade_average` width. The clusteredBar serves
> mainly to expose `Total_Questions` in the tooltip.
>
> **For our rebuild:** render this as ONE horizontal bar (Recharts
> `<BarChart>` horizontal) with `width = grade_average × 100%`, fill =
> `performanceColor(grade_average)`, and a `<Tooltip>` showing
> `Total_Questions` and the % correct/incorrect split. We do NOT need to
> overlay two chart components — that's just a PBIX implementation
> oddity. See §8.

### 4.6 Footer (y ≈ 211.3 – 240)

| # | id | Type | Title / Field | Pos (x,y,w,h) | Hidden? | Notes |
|---|---|------|----------------|---|---|---|
| #4 (group) | 8695561685 | singleVisualGroup `2ca6d33504829e750a95` "Footer" | — | 0, 211.33, 320×29, z=5000 | (V) | Hosts #5 (label), #6 (background bar), #7 (date card). |
| #5 | 8695561686 | textbox | static "Standard Info. Adopted/Revised Date :" (font 10.6667px, color #000000, right-aligned) | 0.26, 0, 261×29 | (V) | parentGroup `2ca6d33504829e750a95`. |
| #6 | 8695561687 | multiRowCard | `dim_standard.blank` (background only) | 0, 1.85, 319.74×25.91 | (V) | Background bar for the footer. Theme color 0 darker −0.3 fill. parentGroup `2ca6d33504829e750a95`. |
| #7 | 8695561688 | card | `Min(dim_standard.lastChangeDateTime)` | 254.96, 1.85, 65.04×23.32 | (V) | The "Adopted/Revised Date" — actually the standard's `lastChangeDateTime` from `dim_standard`. fontSize 8D, theme color 1 (typically dark grey). parentGroup `2ca6d33504829e750a95`. |

### 4.7 Hidden scaffolding (DON'T port these)

| # | id | Type | Why hidden | Notes |
|---|---|------|-----------|-------|
| #2 | 8695561683 | textbox "Description:" | `display.mode:"hidden"` | Redundant label — the description card below is self-explanatory. |
| #9 | 8695561690 | basicShape rectangle (top-right) | `display.mode:"hidden"` | Frame for the Subject/Grade group, hidden in favour of the visible divider. |

These are the only two strictly hidden elements. There are no
`isHidden:true` `singleVisualGroup`s on this page (unlike SDD which has
several legacy template groups).

---

## §5 Scoping & interaction

### Per-card vs per-page filtering

**In the original PBIX:** the page is **per (Subject × Standard)** — every
visual binds to fields that resolve to a single row. Pagination produces
one PDF page per `(Subject, Standard)` combination, optionally further
filtered by Strand if a parent slicer is applied.

**In our rebuild:**

- **KPI strip** (top of page): aggregates **across all standards in the
  filtered scope** (subject/grade/session) — uses `Measure.Total Student`,
  `Measure.Total Standard`, `Measure.Total Question`,
  `Measure.Grade_Average_Standard_Measure`.
- **Two summary bar charts** (single instance, top of page below KPIs):
  the `barChart` + `clusteredBarChart` pair from §4.5, but ONE big chart
  spanning all standards in scope — sorted descending by grade_average,
  with one bar per `cPalms_Standard`.
- **Per-standard card grid**: one card per `cPalms_Standard` in scope,
  rendering the §4.1–§4.6 layout (cPalms code, subject/grade tag, strand,
  cluster, cognitive complexity, # of questions, description, mini-bar,
  adopted date).

### Cross-filter chain

The original page has no cross-filter. The page-level filters list is
empty; the visuals on the per-card render bind directly. Our rebuild
adds optional **client-side strand filtering**: clicking a strand label
in the summary bar chart can scroll/highlight cards in that strand. Keep
this minimal — the primary filter is the React `<ReportFilters>` panel.

### Buttons / drill-through targets

- **No actionButton anywhere on this page.** No "Back to Home", no
  reset, no nav stub. (The SDD page has 3 actionButtons; this page has 0.)
- **No drill-through into other pages** is wired from this page.

For our rebuild, add a "Back to Reports" button at the top via the
shared `<AssessmentReportHeader>` pattern (replaced by a school-wide
`<ReportPageHeader>` since there's no single assessment).

---

## §6 Color thresholds reference

The Standard Summary page uses the project-wide **70% / 80% three-band**
convention, but with a **minor color-hex divergence** vs SDD:

```
Standard Summary chart (#13)              SDD chart (line 12, dax)
< 70%       →  '#FFCCFF'  (pink)          ditto
70%–80%     →  '#faff00'  (yellow)        '#FFFF00' / "Yellow"
≥ 80%       →  '#00ff06'  (green)         '#00FF06'
incorrect   →  theme color 0 darker −0.3  '#CCCCCC'
```

Note the two minor differences:
- Yellow is `#faff00` here (slightly different from SDD's `#FFFF00`/`Yellow`)
- The hex strings are lowercase here (`#00ff06` vs SDD's `#00FF06`)

Both differences are cosmetic — the render is indistinguishable. **For our
rebuild use the existing `performanceColor()` helper from
`frontend/src/lib/reports/colors.ts`** (PERF_PINK / PERF_YELLOW /
PERF_GREEN) — we should not introduce a second color set.

The conditional formatting is **NOT** the DAX `Performance Color Strand`
or `Performance Color Standard2` measure (lines 181, 1043) — it's an
**inline `Conditional.Cases` array** baked into the visual JSON
(line 145–151). The two are equivalent in semantics:

```dax
// 04_dax_measures.dax line 215 (the input to the inline switch)
MEASURE [Grade_Average_Standard_Measure] =
    AVERAGE('cube_question_summary_overall'[Grade_Average])
```

```jsonc
// _layout.full.json line 145, visual #13 (the inline switch)
{ "Conditional": { "Cases": [
  { "Condition": { "And": { "Left": { "Comparison": { "ComparisonKind": 2,
        "Left": { "Measure": { ..., "Property": "Grade_Average_Standard_Measure" }},
        "Right": { "Literal": { "Value": "0D" }}}},
      "Right": { "Comparison": { "ComparisonKind": 3,
        "Left": { "Measure": { ..., "Property": "Grade_Average_Standard_Measure" }},
        "Right": { "Literal": { "Value": "0.7D" }}}}}},
    "Value": { "Literal": { "Value": "'#FFCCFF'" }}},
  { /* 0.7 ≤ x < 0.8 → '#faff00' */ },
  { /* 0.8 ≤ x < 2   → '#00ff06' */ }
]}}
```

> **Edge cases — replicate exactly:**
> - The pink branch is `x > 0 AND x < 0.7` — **a value of exactly 0 is
>   uncolored** (renders default theme color, which is grey). Replicate by
>   treating exact 0 as "no data" and rendering an empty bar.
> - The yellow branch uses **inclusive both sides** (`x >= 0.7 AND x < 0.8`
>   per ComparisonKind=2/=3 semantics in the JSON, where 2=GreaterThanOrEqual
>   and 3=LessThan). The `Performance Color Strand` DAX measure (line 181)
>   uses *strict-both-sides* for the yellow branch — a tiny inconsistency
>   that means a value of exactly `0.7` falls into yellow on this page but
>   into nothing on the SDD treemap. We don't care; our `cellColor()` helper
>   handles `[0.7, 0.8)` → yellow correctly.

---

## §7 Differentiator vs Standards Deep Dive

The user asked: **"How does Standard Summary differ from Standards Deep
Dive?"** Both reports drive off the same cube layer (`cube_standard_summary`,
`cube_question_summary_overall`, `dim_standard`, `dim_strand`) so their
existence side-by-side feels redundant unless we articulate the lens.

| Dimension | Standards Deep Dive (SDD) — page 16 | Standard Summary — page 1 |
|---|---|---|
| **Scope** | **One assessment** (`?item_id=…`). Page filter `dim_item.Item_Name = "Module Assessment: My Community Heroes"` baked in. | **School-wide** (no `item_id`). Filtered only by Subject/Grade/Session. |
| **Grain** | One row per `(strand)` and one row per `(cPalms_Standard)`, both within the single assessment. | One row per `(cPalms_Standard)` aggregated across **all assessments** in the year. |
| **Audience question** | "On THIS assessment, which standards did the school struggle with?" | "Across the WHOLE year, which standards is the school strong/weak on?" |
| **Decision it drives** | Reteach a specific standard before the next module assessment. | Curriculum planning: which standards need more time at the unit level next year? |
| **Time horizon** | Snapshot — one test sitting. | Cumulative — full academic year. |
| **KPI strip** | 5 cards: Total Students + Number of Questions + Number of Standards + Grade Average + Instructor(s). | 4 cards: Total Students + Number of Standards + Number of Questions + Grade Average. (No Instructor card — multiple instructors across many assessments.) |
| **Treemap** | Yes (`# of Standards by Strand`, sized by question count, colored by perf). | No — replaced by a list of per-standard cards. |
| **Bar charts** | THREE 100%-stacked bars, one per perf band (green / yellow / pink), per-standard. | ONE pair of bar charts (correct + incorrect), school-wide, all standards in scope. |
| **Per-standard card** | None — info is in tables and bar charts only. | YES — the entire page is a grid of these. **Each card** shows: cPalms code, Subject/Grade, Strand, Cognitive Complexity, Cluster, # of Questions, full Description, mini grade-average bar, "Adopted/Revised Date". |
| **Drill / cross-filter** | Clicking a treemap tile or per-band bar cross-filters the rest of the page. | None in original. Can add client-side strand filter in our rebuild. |
| **Reuse** | Per-standard rendering can be reused from SDD's `<StandardsRollupTable>` and `CorrectIncorrectBars` (the band bars). | Adds one new rich `<StandardCard>` component; the bar chart and KPI strip can be reused with light tweaks. |
| **PBIX page metadata** | 1280 × 720 canvas, 39 visuals (10+ hidden), interactive. | 320 × 240 canvas, 23 visuals (only 2 truly hidden), paginated. |

**Summary:** SDD answers *"how did this one test go, broken down by
standard?"* Standard Summary answers *"how is the school doing across all
standards we've taught this year, with the standard's full curriculum
metadata visible inline?"* They complement each other — together they cover
the per-assessment AND year-to-date views of the standards lens.

The user needs **both** because:
1. Teachers/curriculum coordinators planning **next** unit need year-to-date
   (Standard Summary).
2. Teachers debriefing the **most recent** assessment need per-assessment
   (SDD).
3. Standard Summary additionally exposes curriculum metadata
   (cPalms code, cluster, Cognitive Complexity, full description, adopted
   date) that SDD does not — making it the canonical "standards reference"
   page even outside score analysis.

---

## §8 Implementation notes for our rebuild

### Backend (FastAPI) — endpoints to add

Add to `backend/app/api/v1/reports.py`:

```python
@router.get(
    "/standard-summary",
    response_model=StandardSummaryPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def standard_summary(
    session: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StandardSummaryPayload:
    """School-wide standards rollup (mirrors PBIX page #1).

    Aggregates cube_standard_summary across all assessments in the
    selected scope and returns one card row per cPalms_Standard plus
    the school-wide KPI strip and a single bar-chart series.
    Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_standard_summary(
        session_filter=session, subject=subject, grade=grade
    )
```

Add a new repo method on `CubeRepository`:

```python
async def get_standard_summary_rollup(
    self,
    session_filter: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
) -> List[Dict[str, Any]]:
    """One row per cPalms_Standard aggregated across all assessments in
    the school (and within the optional session/subject/grade filters).

    Aggregation matches the PBIX measures:
      - num_questions = DISTINCTCOUNT(question_no per standard)
      - grade_average = AVG(cube_question_summary_overall.grade_average)
      - num_assessments = COUNT(DISTINCT item_id) using this standard
    """
    sql = text("""
        WITH scoped_items AS (
            SELECT DISTINCT di.item_id
            FROM dim_item di
            LEFT JOIN dim_subject ds
              ON ds.school_id = di.school_id
             AND ds.subject_id = di.subject_id
            WHERE (CAST(:session_filter AS TEXT) IS NULL OR ds.session = CAST(:session_filter AS TEXT))
              AND (CAST(:subject AS TEXT)  IS NULL OR ds.subject  = CAST(:subject AS TEXT))
              AND (CAST(:grade AS TEXT)    IS NULL OR ds.grade    = CAST(:grade AS TEXT))
        ),
        item_qs AS (
            SELECT DISTINCT qs.school_id, qs.ukey, qs.identifier, qs.item_id
            FROM cube_question_summary qs
            JOIN scoped_items si ON si.item_id = qs.item_id
        ),
        std_q AS (
            SELECT DISTINCT
                iq.ukey, iq.identifier, iq.item_id,
                ds.strand,
                dst.cpalms_standard,
                dst.schoology_standard,
                dst.description,
                dst.cluster,
                dst.cognitive_complexity_rating,
                dst.subject  AS std_subject,
                dst.last_change_date_time
            FROM item_qs iq
            LEFT JOIN dim_strand ds ON ds.identifier = iq.identifier
            LEFT JOIN LATERAL (
                SELECT cpalms_standard, schoology_standard, description,
                       cluster, cognitive_complexity_rating, subject,
                       last_change_date_time
                FROM dim_standard
                WHERE identifier = iq.identifier
                LIMIT 1
            ) dst ON TRUE
            WHERE COALESCE(NULLIF(dst.cpalms_standard, ''),
                           NULLIF(dst.schoology_standard, ''), '') <> ''
        ),
        qso_avg AS (
            SELECT ukey, AVG(grade_average) AS grade_average
            FROM cube_question_summary_overall
            GROUP BY ukey
        )
        SELECT
            COALESCE(NULLIF(sq.cpalms_standard, ''),
                     sq.schoology_standard, '')          AS cpalms_standard,
            COALESCE(sq.schoology_standard, '')           AS schoology_standard,
            COALESCE(sq.strand, '')                        AS strand,
            COALESCE(sq.cluster, '')                       AS cluster,
            COALESCE(sq.cognitive_complexity_rating, '')   AS cognitive_complexity,
            COALESCE(sq.description, '')                   AS description,
            COALESCE(sq.std_subject, '')                   AS subject,
            COUNT(DISTINCT sq.ukey)                        AS num_questions,
            COUNT(DISTINCT sq.item_id)                     AS num_assessments,
            AVG(COALESCE(qa.grade_average, 0))             AS grade_average,
            MAX(sq.last_change_date_time)                  AS last_change_date_time
        FROM std_q sq
        LEFT JOIN qso_avg qa ON qa.ukey = sq.ukey
        GROUP BY 1, 2, 3, 4, 5, 6, 7
        ORDER BY sq.strand, cpalms_standard
        """)
    result = await self.session.execute(sql, {
        "session_filter": session_filter,
        "subject": subject,
        "grade": grade,
    })
    return [_row_to_dict(r) for r in result.all()]
```

Add a school-wide KPI helper that mirrors `Total Student`, `Total Standard`,
`Total Question`, `Grade_Average_Standard_Measure` from §3.

Add a new service method `build_standard_summary()` on `ReportService` that:
1. Calls `cube.get_standard_summary_rollup(...)` to get one row per
   cPalms_Standard.
2. Computes the KPI strip from those rows: `total_standards = len(rows)`,
   `total_questions = sum(r.num_questions)`, `grade_average = AVG(r.grade_average)`.
3. Loads `school_id` school name + logo via existing
   `cube.get_assessment_meta()` pattern (or a new dedicated school-info
   helper `cube.get_school_meta()`).
4. Loads `total_students` from `cube_school_summary` aggregated school-wide
   (`SUM` over all items, then take MAX of `total_students` per item — mirrors
   `Total Student` DAX measure on line 134).

### Backend schemas (`backend/app/schemas/reports.py`)

```python
class StandardSummaryKpis(BaseModel):
    total_students: int
    total_standards: int
    total_questions: int
    grade_average: float
    grade_average_pct: str

class StandardSummaryRow(BaseModel):
    cpalms_standard: str
    schoology_standard: str
    strand: str
    cluster: str
    cognitive_complexity: str  # e.g., "Low" / "Moderate" / "High"
    description: str            # HTML-stripped
    subject: str                # from dim_standard.subject (curriculum subject)
    num_questions: int          # DISTINCTCOUNT question_no for this standard
    num_assessments: int        # COUNT(DISTINCT item_id) where this standard appeared
    grade_average: float
    grade_average_pct: str
    last_change_date_time: Optional[str]   # ISO-format date string

class StandardSummaryPayload(BaseModel):
    school: YTDSchoolInfo                  # reuse existing shape
    kpis: StandardSummaryKpis
    standards: List[StandardSummaryRow]    # one card per standard
```

### Frontend (Next.js + shadcn + Recharts)

**Page entry-point:** `frontend/src/app/app/reports/standard-summary/page.tsx`

```typescript
'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import StandardSummaryKpiStrip from '@/components/app/modules/reports/standard-summary/KpiStrip';
import StandardsBarChart from '@/components/app/modules/reports/standard-summary/StandardsBarChart';
import StandardCard from '@/components/app/modules/reports/standard-summary/StandardCard';

export default function StandardSummaryPage() {
  const [filters, setFilters] = useState({});

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.standardSummary(filters),
    queryFn: () => reportsApi.standardSummary(filters),
  });

  if (isLoading) return <LoadingState label="Loading standard summary…" />;
  if (isError) return <ErrorState message={…} onRetry={() => void refetch()} />;
  if (!data) return null;

  return (
    <ReportCanvas>
      <ReportPageHeader
        logoUrl={data.school.logo_url}
        title="Standard Summary"
        subtitle={`${data.school.name} · ${data.school.current_session}`}
        meta=""
      />
      <ReportFilters value={filters} onChange={setFilters} />
      <StandardSummaryKpiStrip kpis={data.kpis} />
      <StandardsBarChart standards={data.standards} />
      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
        {data.standards.map((std) => (
          <StandardCard key={std.cpalms_standard} std={std} />
        ))}
      </div>
    </ReportCanvas>
  );
}
```

**Components to build** (all under
`frontend/src/components/app/modules/reports/standard-summary/`):

| PBIX visual(s) | New React component | Notes |
|---|---|---|
| #0 (KPI label) → 4-card strip | `<StandardSummaryKpiStrip>` | Same shape as
  `sdd/KpiStrip.tsx` minus the Instructor card. Re-use `<KpiCard>`. |
| #13/#14 bar charts | `<StandardsBarChart>` | Recharts horizontal `<BarChart>` with `dataKey="grade_average"`, one bar per standard, sorted desc. `<Cell fill={performanceColor(grade)}/>` per row. Tooltip shows # of questions and % correct/incorrect. |
| #4 + #11 + #12 + #15 + #19 + #20 + #1 + #5 + #7 + per-card mini bar | `<StandardCard>` | The whole 320 × 240 paginated card, ported as a rich card. Layout: header with cPalms code + subject/grade tag; body with strand, cluster, cognitive complexity, # of questions, full description; mini bar for `grade_average`; footer with "Adopted/Revised Date". Use `bg-card`, `border-border`, semantic Tailwind tokens. |

Reusable from existing:
- `<ReportCanvas>` (shared/ReportCanvas.tsx)
- `<ReportPageHeader>` (shared/ReportPageHeader.tsx) — pass school name/logo
- `<ReportFilters>` (shared/ReportFilters.tsx) — accept session/subject/grade
- `<KpiCard>` (shared/KpiCard.tsx)
- `<LoadingState>`, `<ErrorState>` (shared/)
- `performanceColor()`, `cellColor()` from `lib/reports/colors.ts`
- `tableStyles.ts` if we render any table

### Color tokens

Use the existing palette in `frontend/src/lib/reports/colors.ts`:
- `PERF_GREEN` = `#00FF06` for grade ≥ 0.8
- `PERF_YELLOW` = `'yellow'` for 0.7 ≤ grade < 0.8
- `PERF_PINK` = `#FFCCFF` for grade < 0.7
- `KPI_CARD_BG` = `#B8DBFF` for KPI tile background
- `HEADER_BAR_BG` = `#B8DBFF` for section header bars
- `LAYOUT_BORDER` = `#B3B3B3` for borders
- `INCORRECT_GREY` = `#CCCCCC` for the "incorrect" portion of the bar

Note: the original PBIX page uses `#0E1A77` (deep navy) as the
header-card background for the cPalms code (visual #4, line 44), but our
existing colors.ts doesn't expose this. **Add a new export**:
```ts
export const STANDARD_CARD_HEADER_BG = '#0E1A77';  // deep navy for the cPalms badge
```

### Final canvas geometry (for the new web page, NOT the original 320 × 240)

```
Page header (logo + title + subtitle):     y=0…80
ReportFilters (session/subject/grade):     y=80…140
KPI strip (4 cards, grid-cols-4):          y=140…240
Standards bar chart (full width):          y=240…480 (~240px tall, ~30 bars)
Per-standard card grid (md:grid-cols-2 lg:grid-cols-3): y=480…∞
  Each card ≈ 380 × 320px on desktop
```

Mobile responsive: stack vertically (KPI strip → bar chart →
single-column card list).

---

## §9 Implementation reuse strategy (leveraging SDD plumbing)

Based on §7's comparison, the rebuild can heavily reuse SDD plumbing:

1. **Reuse the cube SQL helpers** in `cube_repository.py`:
   - The new `get_standard_summary_rollup()` is essentially
     `get_standard_rollup_for_item()` (lines 309–367) generalized to
     accept `(session, subject, grade)` instead of `item_id`. Lift the
     CTE structure and replace the `WHERE qs.item_id = :item_id` filter.
2. **Reuse DAX measure semantics:** the same four aggregations
   (`Total Student`, `Total Standard`, `Total Question`,
   `Grade_Average_Standard_Measure`) drive both pages. The only
   difference is the filter context. Keep the formulas identical to
   ensure cross-report number consistency.
3. **Reuse `<KpiCard>` and `<KpiStrip>` shape** — drop the Instructor card,
   keep everything else.
4. **Reuse `<ReportCanvas>`, `<ReportPageHeader>`, `<ReportFilters>`,
   `<LoadingState>`, `<ErrorState>`** verbatim.
5. **Reuse `performanceColor()`** for the bar chart and per-card mini-bar.
6. **The only genuinely new component is `<StandardCard>`** — the rich card
   that surfaces curriculum metadata (cPalms, cluster, cognitive
   complexity, description, adopted date). This metadata isn't shown
   anywhere on SDD, so it's a net-new contribution to the platform.
7. **The standards bar chart** (`<StandardsBarChart>`) is a school-wide
   variant of SDD's `<CorrectIncorrectBars>` (which is per-band,
   per-assessment). Adapt the existing component or write a new one — the
   former is preferred for visual consistency with SDD's three-band bar.

If we follow this reuse strategy, the new page should be ~150–200 lines of
React + ~60 lines of new SQL + ~30 lines of new schema/service code.
The bulk of the visual fidelity comes free from existing primitives.

---

## §10 Cross-references

| What | Where |
|---|---|
| Page object & visual JSON | `_layout.full.json` lines **5 – 243** |
| Visual list (summary, ord 14) | `20_pages.md` lines 1–55 (under "## Standard Summary") |
| Visual list (JSON, full fields) | `20_pages.json` lines 1–276 |
| Per-page field map | `22_fields_per_page.json` lines 2–50 |
| DAX measures (cited inline) | `04_dax_measures.dax` — `Total Student` line 134, `Total Question` line 148, `Total Standard` line 159, `Performance Color Strand` line 181, `Grade_Average_Strand_Measure` line 203, `Grade_Average_Standard_Measure` line 215, `Performance Color Standard` line 250, `H3 - Total Students` line 272, `H3 - # of  questions` line 293, `H3 - # of standards` line 302, `Total Question Standard` line 371, `Total Question Strand` line 405, `Total Standard by Strand` line 432, `Incorrect_Grade_Average_Standard_Measure` line 551, `Performance Color Standard2` line 1043 |
| Power Query M | `07_power_query.m` — `dim_item` filter line 32, `dim_subject` line 53, `dim_strand` line 76, `dim_standard` (with HTML-stripped `Custom.CleanedDescription`) line 116, `cube_standard_summary` line 22, `cube_question_summary_overall` (HTML-stripped Description) line 161 |
| `dim_standard` schema | `03_schema.csv` lines 158–173 (15 columns: Cognitive_Complexity_Rating, Direct_Link, Grader, Identifier, Language, Schoology_Standard, Standard_New, Strand, Subject, cPalms_Standard, cluster, description, lastChangeDateTime, rundate, Custom.CleanedDescription, uniquesID) |
| `cube_standard_summary` schema | `03_schema.csv` lines 114–123 (10 columns: Strand_ID, Identifier, Total_Questions, Total_Standards, Total_Possible_Point, Total_Score, Grade_Average, Percentage_InCorrect_Answers, ID, Item_ID) |
| `dim_strand` schema | `03_schema.csv` lines 174–177 (4 columns: Identifier, Strand, strand_ID, ID) |
| Companion analysis | `REPORT.md` §6 lines 230–254 (page list); §3 lines 65–94 (table inventory) |
| SDD spec (mirror this file's structure) | `50_sdd_spec.md` — page-level spec at the same depth |
| Backend repository pattern to extend | `backend/app/repositories/cube_repository.py` — `get_standard_rollup_for_item()` lines 309–367 is the closest existing helper |
| Backend service pattern to extend | `backend/app/services/report_service.py` — `build_standards_deep_dive()` lines 321–400 is the closest existing helper |
| Frontend reuse — KpiCard | `frontend/src/components/app/modules/reports/shared/KpiCard.tsx` |
| Frontend reuse — KpiStrip pattern | `frontend/src/components/app/modules/reports/sdd/KpiStrip.tsx` |
| Frontend reuse — bar chart pattern | `frontend/src/components/app/modules/reports/sdd/CorrectIncorrectBars.tsx` |
| Frontend reuse — ReportFilters | `frontend/src/components/app/modules/reports/shared/ReportFilters.tsx` |
| Frontend reuse — ReportCanvas / Header | `frontend/src/components/app/modules/reports/shared/ReportCanvas.tsx`, `ReportPageHeader.tsx`, `AssessmentReportHeader.tsx` |
| Color palette | `frontend/src/lib/reports/colors.ts` |
| Existing SDD page (reference) | `frontend/src/app/app/reports/standards-deep-dive/page.tsx` |

---

*Generated 2026-05-15 from `data/Assessment Analysis Dashboard.pbix` extracts.
Re-run `_extract.py` + `_layout.py` from this directory to refresh source
files.*
