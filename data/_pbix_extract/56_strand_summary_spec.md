# Strand Summary — Implementation Spec

> **Scope:** PBIX page #15 (REPORT.md "Page 2") *"Strand Summary"* in
> `data/Assessment Analysis Dashboard.pbix`. Source-of-truth files cited
> inline.
>
> **Audience:** an implementer building the Next.js + Recharts replica at
> `frontend/src/app/app/reports/strand-summary/page.tsx`. School-wide,
> cross-assessment lens — complementary to the per-assessment "Standards
> Deep Dive" (SDD) and the school-wide per-standard "Standard Summary".

---

## §1 Page-level metadata

- **Layout JSON path:** `_layout.full.json` lines 245–492 (page object).
  - `id: 282753156`, internal `name: "f91d5b85996210139258"`,
    `displayName: "Strand Summary"`, `ordinal: 15`, `objectId:
    "5a468448-dd59-4773-b0f0-a78b0d95a37e"`.
- **Canvas:** `320 × 240` (`width`/`height` lines 485–486). **Paginated
  RDL** size — small PNG/PDF tile, NOT the 1280×720 interactive canvas
  that SDD/QRA Interactive use. The tile renders inside the
  paginated-report frame (multi-page printable; one tile per
  Strand × Assessment combination chosen by the parent RDL).
- **Page background:** none — no `outspace.color` on the page `config`,
  which is just `{"visibility":1,"type":1}` (line 487).
- **Visual containers:** 24 (matches REPORT.md §6 "Page 2, 24 visuals,
  working (paginated)"). Of those, ~3 are `singleVisualGroup` containers
  (no rendered chrome of their own, just nest other visuals); ~21 render
  as actual visuals + chrome.
- **Page-level filters:** `filters: "[]"` (line 484) — **no page filter**.
  All scoping comes from the parent RDL when the report is rendered (the
  RDL feeds one strand-row context per render via the relationship to
  `dim_strand`/`dim_standard`/`dim_subject`). On screen during direct
  preview the page shows the school-wide overall rollup.
- **No `slicer` visualType anywhere on the page.** Filtering is done
  exclusively by the parent paginated-report context. There is no Filter
  Pane interaction either — `22_fields_per_page.json` lines 51–103 lists
  zero `Categorical`/`Advanced` page-level filters.

> **Implication for the rebuild (§2 below):**
> The Strand Summary page is **school-wide** (no `Item_ID` baked in, no
> `Strand_ID` / `Identifier` page filter). In the original PBIX it
> renders one tile per `dim_strand[Strand]` value as part of a paginated
> RDL. In our Next.js rebuild we collapse that to a single school-wide
> page that lists ALL strands as rows in a Strand-grain rollup, with
> Subject / Grade / Session filters at the top driving the dataset.

---

## §2 Slicers / filter pane

**There are zero slicer visuals on this page** and **zero page-level
filters** (`filters` on the page object is `"[]"`, line 484; per-visual
filter counts are 0–2).

The "filtering" the original PBIX relies on:

- **Parent paginated-report (RDL) page filter** — sets the
  `dim_strand[Strand]` (and indirectly `dim_subject[Subject]`,
  `dim_subject[Grade_no]`) context, one tile per strand. The RDL is
  outside this page (one of the `Year To Date - Longitudinal Report*` /
  `Question Summary Report*` pages at ords 6–14 hosts the rdlVisual,
  which embeds this Strand Summary page as a sub-report).
- **Subject + Grade chrome** — the `multiRowCard`s for
  `dim_subject.Subject` and `dim_subject.Grade_no` (visuals #14, #15,
  see §4.5) are *display* echoes of the RDL filter context; they do not
  themselves filter (they have no `filters`).

Our Next.js rebuild therefore exposes:

- A **header filter bar** (`<ReportFilters>` from
  `frontend/src/components/app/modules/reports/shared/ReportFilters.tsx`,
  fields: Session, Category/Assessment_type, Subject, Grade, Section).
  Default = no filter → school-wide rollup across the whole academic
  year that's loaded.
- These filters are passed as query-string params to the new
  `/api/v1/reports/strand-summary` endpoint and propagate down through
  the cube join (`dim_subject` → `dim_item` → `cube_standard_summary`).
- **No** assessment selector (this report is intentionally
  cross-assessment).
- **No** click-through cross-filter inside the page (mirrors the
  paginated original — clicks on the bars don't re-filter neighbouring
  visuals).

---

## §3 KPI / header strip (top row, y ≈ 0–95)

The page is a tile, so the "KPI strip" is small. There is **no large
"Total Students / Grade Average" KPI bar** like SDD has. Instead the
top strip is composed of label-style `multiRowCard`s plus the Strand
header. Coordinates from `_layout.full.json` lines 245–410.

| # | Title (visible text) | Position (x,y,w,h) | Field / Measure | Source measure |
|---|----------------------|--------------------|-----------------|----------------|
| #6 | **Strand** name banner (e.g. `"Algebraic Reasoning"`) | 0, 0, 319.91 × 31.0 | `dim_standard.Strand` | direct column (multiRowCard, dark-blue chrome `#0E1A77` background; in this build `vcObjects.background.show=false` so it renders transparent over the page) |
| #1 | **# of standards** label | 0, 91.51, 319.66 × 23.72 | `Titles.H3 - # of standards` | DAX literal `"Number of Standards: " & CALCULATE('Measure'[Total Standard])` |
| #2 | **# of standards** label (questions variant — visible text "# of standard") | 0, 70.89, 319.66 × 25.0 | `Titles.H3 - # of  questions` | DAX literal — `Titles` table, same shape: `"Number of Questions: " & [Total Question]` (note: the field name has a double-space typo `"# of  questions"` and is mislabelled "# of standard" in vcObjects.title) |
| #14 | **Subject** label | 0, 2.32 (inside group), 132.24 × 22.69 | `dim_subject.Subject` | direct column (multiRowCard, light-pill style, no background) |
| #15 | **Grade_no** label | 132.24, 2.30 (inside group), 18.91 × 22.75 | `dim_subject.Grade_no` | direct column (multiRowCard, no background). `Grade_no` is the calc col `RIGHT([Grade], 1)` — just the digit/K |
| #7 | **Last-changed timestamp** card | 254.96, 1.85 (inside footer group), 65.04 × 23.32 | `Min(dim_standard.lastChangeDateTime)` | aggregation, formatted as date — diagnostic timestamp showing when `dim_standard` was last refreshed by the Schoology pipeline |

> **There is NO "Total Students" / "Grade Average" / "Number of
> Questions" big-card row on this page.** Compare to SDD §3 which has 4
> sky-blue KPI cards. Strand Summary is a "small tile" and uses
> `Titles.H3 - …` text-only echoes instead. The numeric values do appear
> inside those echo strings though, so the consumer sees `"Number of
> Standards: 12"` etc.

For our rebuild we **upgrade** this: render a 4-card KPI strip
(re-using `<KpiStrip>` from the SDD module styling) at the school-wide
grain. See §8.

---

## §4 Visual-by-visual catalogue

Coordinates and z-order from `_layout.full.json` lines 245–481.
Annotations: **(VISIBLE)** = renders at runtime; **(HIDDEN)** =
`display.mode:"hidden"` set in singleVisual. Visual indices reflect
position in `20_pages.json` "Strand Summary" (lines 282–584) so callers
can cross-reference.

### 4.1 Header band (y < 32)

| # | Type | Title / Field | Pos (x,y,w,h) | Hidden? | Notes |
|---|------|----------------|---|---|---|
| #6 | multiRowCard | `dim_standard.Strand` | 0, 0, 319.91 × 31.0 | (V) | Strand banner; vcObjects.background.show=false but `color:'#0E1A77'` is configured so a Subject Grade banner build could re-enable. In this PBIX build it renders transparent. |
| #14+15 (group #11 `d2d373f10348244a6b33` "Subject & Grade") | multiRowCard ×2 | `dim_subject.Subject`, `dim_subject.Grade_no` | 168.85, 0, 151.15 × 26.95 (group); inside: subject 0–132, grade 132–151 | (V) | Two stacked label cards on the right of the header band |
| (basicShape inside #11) | basicShape `rectangle` (vertical separator) | 126.02, 0, 12.18 × 26.95 | (V) | Thin grey vertical bar separating Subject card from Grade card |
| (basicShape inside #11) | basicShape `rectangle` border | 3.87, 5.16, 147.20 × 16.50 | **(H)** `display.mode:"hidden"` | unused box; legacy scaffolding |

### 4.2 Title row (y ≈ 70–115)

| # | Type | Field | Pos (x,y,w,h) | Hidden? | Notes |
|---|------|-------|---------------|---------|-------|
| #2 | multiRowCard | `Titles.H3 - # of  questions` (note: title text reads "# of standard") | 0, 70.89, 319.66 × 25.0 | (V) | Border-on style, `vcObjects.title.show=false`. Renders the dynamic text e.g. *"Number of Questions: 12"*. |
| #1 | multiRowCard | `Titles.H3 - # of standards` | 0, 91.51, 319.66 × 23.72 | (V) | Border-off style. Renders e.g. *"Number of Standards: 12"*. |

### 4.3 Strand-bar primary visual — visual #0 **(VISIBLE)**

This is the page's "headline" chart — a **horizontal bar chart of
Incorrect % per Standard** in the strand context.

- **Type:** `barChart` at `(0, 4, 151 × 62)`, z=2000.
  - Layout JSON line 248–254 (visual id `8695561665`).
- **Title text:** `"Correct and Incorrect % by Standards"` but
  `vcObjects.title.show:false` — title is hidden in this build.
- **Category (Y-axis):** `dim_standard.cPalms_Standard` (one bar per
  standard within the strand context).
- **Y / Value:** `Measure.Incorrect_Grade_Average_Standard_Measure`
  - DAX (line 551, `04_dax_measures.dax`): `1 - [Grade_Average_Standard_Measure]`
  - Where `Grade_Average_Standard_Measure` = `AVERAGE('cube_question_summary_overall'[Grade_Average])` (line 243).
- **Sort:** `OrderBy` the value descending — worst-performing
  (most-incorrect) standard at the top of the bars.
- **Data-point color rule** (per-bar conditional, NOT per-band like
  SDD's three charts): a `Conditional` expression on
  `Grade_Average_Standard_Measure`:
  - `<0.7 && >0` → `'#FFCCFF'` (pink)
  - `[0.7, 0.8)` → `'#faff00'` (PBIX-yellow variant — note the lowercase
    `f` and slightly different hex from SDD's `#FFFF00`; effectively
    yellow either way)
  - `[0.8, 2.0)` → `'#00ff06'` (green)
  - The first selector entry uses the ghost ref
    `selector.metadata = "Key Measures.% of incorrect answer"` and is a
    no-op fallback (the live model has no `Key Measures` table).
- **Value-axis end:** `1D` (i.e. 100%). Axis itself hidden.
- **Category axis hidden** (`show:false`); labels shown inside bars
  (`labels.show:true`, position `'InsideEnd'`, fontSize 8D, precision 1
  decimal).
- **Legend:** bottom-center, fontSize 8D.
- **Filters:** `"[]"` (no advanced filter on this primary chart).
- **Tooltip:** custom `'ReportSection9f325cd482d41bd17529'` linked but
  `show:false`.

### 4.4 The "100% Stack 2" group — visual group `4a0e0aedd03c7d221ca3` **(VISIBLE)**

A `singleVisualGroup` at `(0.26, 110.33, 319.66 × 114.72)`, z=8000,
displayName `"100% Stack 2"`. Two `columnChart`s stacked at the same
position (z-index swap):

| sub-#  | Type | Pos (x,y,w,h) inside group | Y-series | Category | Color rule |
|--------|------|----------------------------|----------|----------|------------|
| #9 (id 8695561712) | **columnChart** | 0, 0, 319.31 × 114.84, z=0 | `Sum(cube_standard_summary.Percentage_InCorrect_Answers)` (and `Sum(cube_standard_summary.Grade_Average)` as Tooltip) | `dim_standard.cPalms_Standard` | `display.mode:"hidden"` — **this is the "incorrect %" overlay**, hidden in this build. Theme grey fill. |
| #10 (id 8695561713) | **columnChart** | 0, 0, 319.31 × 114.84, z=1000 | `Measure.Grade_Average_Standard_Measure` | `dim_standard.cPalms_Standard` | **VISIBLE.** Same per-row Conditional 70/80 traffic-light fill as visual #0 (`#FFCCFF` / `#faff00` / `#00ff06`). Order: descending by Grade Average. |

The intent of the group: render the **vertical column chart** of correct
% per standard at the top half of the page (y=110…225). The "incorrect
overlay" was an earlier draft (#9) the author hid.

- Both charts: legend bottom-center, value-axis end `1D` for the visible
  green chart and `0.06D` for the hidden incorrect overlay (a tiny axis
  scale that suggests the overlay was meant to render only very small
  bars).
- Visible chart: data labels `OutsideEnd` at fontSize 8D, color theme.
- Filters: `"[]"` on both.

> **Why two columnCharts on top of each other?** PBI doesn't natively do
> stacked correct/incorrect column with per-bar custom color. The author
> tried two charts at the same coords (one for correct, one for
> incorrect, semi-transparent) — but the incorrect overlay is hidden in
> this build. The visible chart shows only the **correct %** per
> standard.

### 4.5 The "Subject & Grade" chrome group — visual group `d2d373f10348244a6b33`

Already covered in §3 / §4.1. Wraps the Subject + Grade label cards in
the top-right header.

### 4.6 The "100% Stack 2" #2 — visual group `b45a8b9ed650cb0da334` **(VISIBLE)**

A second `singleVisualGroup` at `(169, 61, 151 × 62)`, z=7000,
displayName `"100% Stack 2"` (yes, same name as 4.4 — the author cloned
the container). Two charts inside:

| sub-#  | Type | Pos | Y-series | Category | Notes |
|--------|------|-----|----------|----------|-------|
| #17 (id 8695561720) | **clusteredBarChart** | 0, 0, 151 × 62 | `Measure.Grade_Average_Standard_Measure` | `dim_standard.cPalms_Standard` | Visible, traffic-light per-bar fill (`#FFCCFF`/`#faff00`/`#00ff06`). Order desc. Value axis end 1D. **A small horizontal-bar mini-chart of correct %**. |
| #18 (id 8695561721) | **barChart** | 0, 0, 150.89 × 61.5 | `Measure.Incorrect_Grade_Average_Standard_Measure` | `dim_standard.cPalms_Standard` | Visible, theme-grey fill (no traffic-light). Two advanced filters: `Incorrect_Grade_Average_Standard_Measure IS NOT NULL` and `Grade_Average_Standard_Measure IS NOT NULL`. Order desc. Detail data labels render `Incorrect_Grade_Average_Standard_Measure` as a dynamic per-bar label using `dynamicLabelDetail`. **A small horizontal-bar mini-chart of incorrect %**. |

This is a **paired correct/incorrect mini-chart** at the top-right of
the page (coords absolute on the page: x=169…320, y=61…123). They sit
inside the same cell as the columnChart group #10 above.

### 4.7 The "Footer" group — visual group `37f0f48d6dc927d61479`

A `singleVisualGroup` at `(0, 212.10, 320 × 27.76)`, z=1000, displayName
`"Footer"`. Wraps the bottom rows of the page (lines 296–325):

- **textbox** *"Standard Info. Adopted/Revised Date :"* (line 303, x=0.26, y=0, w=260.7, h=27.6, font 8pt black, right-aligned). Background hidden.
- **multiRowCard** bound to `dim_standard.blank` (id 8695561709, x=0, y=1.85, w=319.74, h=25.91). The `[blank]` measure is a placeholder (PBIX dev leftover). vcObjects.background uses theme `ColorId:0, Percent:-0.3` (neutral grey). vcObjects.title.show=false. Renders a thin neutral-grey strip behind the textbox.
- **card** bound to `Min(dim_standard.lastChangeDateTime)` (id 8695561710, x=254.96, y=1.85, w=65.04, h=23.32). 8D font, no background, no title — appears as a small date string at the right end of the footer bar (the "Adopted/Revised Date" actual value).

### 4.8 The "Top Subdetails" group — visual group `555e8cb5cb39da5da08d` **(VISIBLE)**

A `singleVisualGroup` at `(0, 26.81, 319.66 × 44.13)`, z=4000, displayName
`"Top Subdetails"`. This is the **Cluster + Cognitive Complexity** strip
that sits between the Strand banner (#6) and the "# of standards" label
(#1). Lines 442–481.

| sub | Type | Pos | Field expression | Notes |
|------|------|------|------------------|-------|
| #20 (8695561723) | card | 5.41, 5.72, 290.01 × 18.56, z=3000 | titlebar text expr: `Min(dim_standard[cluster])` | Renders "Cluster:" string from `dim_standard.cluster` aggregation. The Values projection is `[blank]` (just a placeholder); the actual rendered text comes from the title's `Aggregation` expression. |
| #21 (8695561724) | multiRowCard | 0, 0, 319.66 × 44.08, z=0 | `dim_standard.blank` | Background neutral grey (theme ColorId:0 -0.3). The grey strip background for the row. |
| #22 (8695561725) | basicShape (line, rotated 90°) | 0.26, 15.0, 300.84 × 18.56, z=2000 | — | Vertical divider between the Cluster card and the Cognitive Complexity card. lineColor theme grey -0.5, weight 1D. |
| #23 (8695561726) | card | 4.9, 25.57, 290.01 × 18.56, z=1000 | titlebar text expr: `Min(dim_standard[Cognitive_Complexity_Rating])` | Renders "Cognitive Complexity Rating:" string from `dim_standard.Cognitive_Complexity_Rating`. |

Both card visuals exploit the trick of feeding `dim_standard.blank` (a
dummy measure that returns nothing visible) as the Values, then using
`vcObjects.title.text` with an `Aggregation` `Min(column)` expression to
render the *real* text. This lets PBI show two text rows in one card
without using a tableEx.

### 4.9 Hidden / scaffolding

- The first `basicShape` inside the Subject & Grade group (#11), id
  8695561715, has `display.mode:"hidden"` (line 371). Pure leftover.
- The first columnChart in the "100% Stack 2" group (#9, id 8695561712)
  has `display.mode:"hidden"` (line 342). The "incorrect overlay" the
  author abandoned.

There is no hidden Reset/Bookmark button on this page (unlike SDD §4.6
visual #12).

---

## §5 Scoping & interaction

### What grain is each visual?

The **PBIX page itself has no Item / Strand filter**, so the Strand
Summary tile renders **across all assessments and all strands** on
direct preview. When embedded in the parent RDL it inherits the RDL's
per-tile filter context — typically one tile per `(dim_subject.Subject,
dim_subject.Grade, dim_strand[Strand])` triple.

In our rebuild we drop the per-tile rendering and produce one
school-wide page that lists all strands. So:

- **Top KPI strip (rebuilt — §8):** aggregates across all assessments
  in the loaded academic year for the chosen Subject / Grade / Session
  filters.
- **Strand banner (#6):** in the rebuild this becomes the page H1 (e.g.
  *"Strand Summary"*) — we don't render one tile per strand.
- **Bar chart #0 (Incorrect % per Standard):** in the rebuild collapses
  to either (a) drop-replace with **one bar per Strand** (which is the
  whole point of "Strand Summary" — a strand-grain rollup), or (b) keep
  per-Standard but list ALL standards across the school. Per the
  product brief and the "Strand Summary" name, option (a) is correct:
  **one bar per Strand**, value = `1 − avg(grade_average) per Strand`.
- **Vertical columnChart #10 (Correct % per Standard):** rebuild as
  **one column per Strand**, value = `avg(grade_average) per Strand`.
  Color = traffic-light from `performanceColor()`.
- **Mini horizontal pair (#17 + #18):** these duplicate #10/#0 at small
  size; in our single-page rebuild we collapse them away (they exist in
  the PBIX only because the paginated tile is 320×240 and the author
  needed two compact summary mini-charts). We can render them as a
  small inline summary card OR simply omit them. **Recommendation:
  omit** — the main charts already convey the same data.
- **Cluster / Cognitive Complexity row (#20–#23):** these only make
  sense in the per-tile context (the tile is rendered for ONE
  Standard within the Strand). In our school-wide rollup the Strand
  doesn't have a single "Cluster" or "Cognitive Complexity Rating"
  value — it's an aggregation of many standards. **Drop these in the
  rebuild.**
- **Footer (#7 last-change date + textbox):** purely diagnostic. Can
  surface as a small "data refreshed: {date}" footer at the bottom of
  the page. Not load-bearing.

### Interaction

- The PBIX page has **zero cross-filter behaviour** (no slicer; no
  click-through; no bookmark/Reset button). Clicks on the bars do
  nothing in the rendered tile.
- Our rebuild keeps that simplicity — no click-through. The header
  filter bar is the only interactive element.

---

## §6 Color thresholds reference

Strand Summary uses the same project-wide **70% / 80% three-band**
convention as every other page.

```
< 70%       →  PINK    "#FFCCFF"   ← under-performing
70%–80%     →  YELLOW  "#faff00" / "#FFFF00"  (PBIX uses both — same hue)
≥ 80%       →  GREEN   "#00FF06" / "#00ff06"
incorrect   →  GREY    theme grey (ColorId 0, Percent -0.3)
```

The **conditional fills are inline on each visual** rather than
referencing the `Performance Color *` measures. The key DAX expression
embedded inside `_layout.full.json` (lines 254, 352, 420) for visuals
#0, #10, #17 is identical:

```
SWITCH(TRUE(),
  Grade_Average_Standard_Measure > 0  AND < 0.7  → '#FFCCFF',
  Grade_Average_Standard_Measure >= 0.7 AND < 0.8 → '#faff00',
  Grade_Average_Standard_Measure >= 0.8 AND < 2.0 → '#00ff06'
)
```

That's a **per-bar / per-column conditional fill keyed off the
measure**, applied with selector `data.dataViewWildcard.matchingOption=1`.

> **Edge case:** the conditional uses `> 0 AND < 0.7` for pink, so a
> grade_average of exactly **0** falls into NO band (renders default
> theme color, which is grey). The yellow branch is `>= 0.7 AND < 0.8`
> (inclusive on the lower bound). The green branch is `>= 0.8 AND <
> 2.0`. **Replicate this exactly via `performanceColor()` in
> `frontend/src/lib/reports/colors.ts`** — current implementation is
> `<0.7 → pink, <0.8 → yellow, else green` which slightly differs at
> exactly 0 (current returns pink). For Strand Summary this is fine
> because we filter out zero-question rows before rendering anyway.

For background reference see DAX measures `Performance Color Strand`
(`04_dax_measures.dax` lines 181–197) and `Performance Color Standard2`
(lines 1043–1056). Both wrap the same SWITCH around
`Grade_Average_Standard_Measure`.

---

## §7 Differentiator vs SDD AND vs Standard Summary

The user ships **three sibling reports** that look superficially similar
("a bunch of bars colored by traffic light") but answer **three
distinct questions**. This section is the canonical reference for which
one to open when.

### 7.1 The three reports at a glance

| Report | Page in PBIX | Scope | Grain (one row per…) | What it answers |
|--------|--------------|-------|----------------------|-----------------|
| **Standards Deep Dive (SDD)** | ord 1 (Standards Deep Dive interactive), 39 visuals, 1280×720 | **One assessment** (single `Item_ID` baked into page filter) | Strand AND Standard within that assessment | *"For THIS assessment, which standards / strands tripped students up?"* |
| **Standard Summary** | ord 14 (Standard Summary), 23 visuals, 320×240 paginated | **School-wide** (no Item filter; one tile per `(Strand, Standard)` from RDL context) | One **Standard** (e.g. `MA.5.NBT.2`) across all assessments | *"For THIS standard, how is the school doing across the year?"* |
| **Strand Summary** | ord 15 (Strand Summary), 24 visuals, 320×240 paginated | **School-wide** (no Item filter; one tile per `Strand` from RDL context) | One **Strand** (e.g. `Algebraic Reasoning`) across all assessments | *"For THIS strand, how is the school doing across the year? Which standards within the strand drag the strand average down?"* |

### 7.2 Why all three exist (the user value)

- **SDD = depth on one assessment.** When a teacher just gave a quiz
  and wants to know which standards bombed, they open SDD with
  `?item_id=…`. Both strand and standard breakdowns side-by-side, plus
  the 3 traffic-light "performance band" panels (green ≥80%, yellow
  70–80%, pink <70%). Per-assessment lens.
- **Standard Summary = year context for one standard.** When a coach is
  remediating a specific standard (say `MA.5.NBT.2`) across the school,
  they want a year-long view of that one standard — every assessment
  that touched it, what % correct, drift over time. Per-standard,
  cross-assessment lens.
- **Strand Summary = year context for one strand (broader bucket).**
  When the same coach wants to step UP a level — *"is our whole
  Algebraic Reasoning strand weak this year, or is it just the one
  NBT.2 standard?"* — they open Strand Summary. Strand is a coarser
  grouping than Standard: `dim_strand` has 7,071 rows mapping
  identifiers to strand names while `dim_standard` has 7,958 rows of
  individual standards (REPORT.md §3.3). One strand contains many
  standards; this page rolls them up.

### 7.3 Differentiator from SDD

| Axis | SDD | Strand Summary |
|------|-----|----------------|
| Page filter | `dim_item.Item_Name` baked in (per-assessment) | None (school-wide) |
| Total Students card | Yes (sky-blue 4-card KPI strip) | No (text-only `Titles.H3 - …` echoes) |
| Strand treemap | Yes (`#11` 465×177 px) | No |
| 100% stacked bars per band | Yes (3 charts, one per band) | No |
| Per-Standard Charticulator row strip | Yes (`#36`) | No |
| Per-Strand Charticulator row strip | Yes (`#35`) | Implicit via the bar/column charts |
| Bar chart of Incorrect % per Standard | No | **Yes — primary visual #0** |
| Vertical column chart of Correct % per Standard | No | **Yes — visual #10** |
| Mini paired correct/incorrect bars | No | **Yes — visuals #17/#18** |
| Cluster + Cognitive Complexity strip | No | **Yes (per-tile only — drop in rebuild)** |
| Canvas size | 1280×720 (interactive) | 320×240 (paginated) |
| Grain in rebuild | per-Standard (within the chosen assessment) | per-Strand (across all assessments) |

### 7.4 Differentiator from Standard Summary

| Axis | Standard Summary | Strand Summary |
|------|------------------|----------------|
| Per-tile context (PBIX) | one tile per (Strand, Standard) | one tile per Strand |
| Banner visual | `dim_standard.cPalms_Standard` (the standard code, e.g. `MA.5.NBT.2`) | `dim_standard.Strand` (the strand name, e.g. `Algebraic Reasoning`) |
| Header echo cards | `Description` (the standard's text) and `Cluster` | `Subject` + `Grade_no` |
| Sub-detail row | one (no sub-detail row, since the standard IS the leaf) | per-Standard breakdown WITHIN the strand |
| Visual mix (REPORT.md §6 ord 14 vs 15) | barChart×1 + clusteredBarChart×1 | barChart×2 + columnChart×2 + clusteredBarChart×1 (more chart-heavy because it has more standards to render) |
| Rebuild grain | one row per (school × standard) collapsed across all assessments | one row per (school × strand) collapsed across all assessments |
| Use case | "Is my school weak on MA.5.NBT.2 this year?" | "Is my school weak on Algebraic Reasoning broadly this year?" |

> **Pitfall:** in the live PBIX both Standard Summary and Strand Summary
> are 320×240 paginated tiles whose visuals look almost identical at
> first glance — same color palette, same chart families. The DIFFERENCE
> is the **grain** (Standard vs Strand) and the **detail visuals**
> (Strand Summary has BOTH a "% per Standard" bar AND a "% per
> Standard" column chart, so the consumer sees the same data twice in
> two orientations — one for sorted-by-incorrect, one for
> sorted-by-correct). Standard Summary skips the per-Standard
> breakdown because there's only one standard per tile.

### 7.5 Why the user needs all three

A literal walk-through:

1. **Coach opens YTD dashboard** → sees overall school avg dropped 4 pts
   over the year.
2. **Coach opens Strand Summary** (no filter) → sees Algebraic Reasoning
   (avg 64%, **pink**) and Geometry (avg 71%, **yellow**) are dragging
   the whole school down. Other strands are green.
3. **Coach opens Standard Summary** filtered to standards within
   Algebraic Reasoning → sees `MA.5.NBT.2` (avg 51%, **pink**) is the
   single worst-performing standard pulling the strand down.
4. **Coach opens an assessment that included `MA.5.NBT.2`** → opens SDD
   for that assessment → sees per-question breakdown of which questions
   on that assessment hit `MA.5.NBT.2` and what wrong answers students
   gave.

That's the "drill-down hierarchy": **Strand Summary → Standard Summary
→ SDD → Question Response Analysis**. Each report is the entry point
for a different level of "Why is the school underperforming?".

---

## §8 Implementation notes for our rebuild

### Backend (FastAPI) — endpoints to add

```
GET /api/v1/reports/strand-summary
    ?session=2025-26&subject=Math&grade=5&category=Module%20Assessment&section=…
    → all params optional; returns the school-wide rollup
```

Return shape (Pydantic) — add to `backend/app/schemas/reports.py`:

```python
class StrandSummarySchoolRow(BaseModel):
    """One row per Strand for the whole school (filtered by query params)."""
    strand: str
    num_standards: int           # COUNT(DISTINCT identifier) within strand
    num_questions: int           # COUNT(DISTINCT ukey) within strand
    num_assessments: int         # COUNT(DISTINCT item_id) where this strand appears
    grade_average: float         # AVG(cube_question_summary_overall.grade_average)
    grade_average_pct: str       # _format_pct(grade_average)
    incorrect_pct: float         # 1 - grade_average
    perf_color: str              # "#FFCCFF" | "#faff00" | "#00ff06" | "" (the 70/80 traffic-light hex)


class StrandSummaryStandardRow(BaseModel):
    """One row per (strand, cPalms_Standard) for the whole school — drives the secondary table.
    
    Same shape as SddStandardRow but cross-assessment.
    """
    strand: str
    cpalms_standard: str
    schoology_standard: str
    num_questions: int
    num_assessments: int
    grade_average: float
    grade_average_pct: str
    perf_color: str


class StrandSummaryKpis(BaseModel):
    total_strands: int
    total_standards: int
    total_questions: int
    total_assessments: int
    total_students: int
    grade_average: float
    grade_average_pct: str


class StrandSummaryFilters(BaseModel):
    session: Optional[str] = None
    subject: Optional[str] = None
    grade: Optional[str] = None
    category: Optional[str] = None     # = dim_subject.assessment_type
    section: Optional[str] = None


class StrandSummaryPayload(BaseModel):
    school: YTDSchoolInfo               # reuse existing
    filters_applied: StrandSummaryFilters
    kpis: StrandSummaryKpis
    strands_rollup: List[StrandSummarySchoolRow]
    standards_rollup: List[StrandSummaryStandardRow]
```

Add a route handler in `backend/app/api/v1/reports.py`:

```python
@router.get(
    "/strand-summary",
    response_model=StrandSummaryPayload,
    dependencies=[Depends(require_permission("reports:read"))],
)
async def strand_summary(
    session: Optional[str] = None,
    subject: Optional[str] = None,
    grade: Optional[str] = None,
    category: Optional[str] = None,
    section: Optional[str] = None,
    db: AsyncSession = Depends(get_db_with_rls),
) -> StrandSummaryPayload:
    """School-wide strand rollup (mirrors PBIX page #15).

    All filter params are optional; default returns the whole-school
    rollup across the loaded academic year. Requires: reports:read.
    """
    service = ReportService(db)
    return await service.build_strand_summary(
        StrandSummaryFilters(session=session, subject=subject, grade=grade,
                             category=category, section=section)
    )
```

Add a service method `build_strand_summary` in
`backend/app/services/report_service.py` that:

1. Calls a new repo method `get_school_strand_rollup(filters)` that
   composes the filtered SQL (apply Subject / Grade / Session / Section
   joins through `dim_subject` ↔ `dim_item` ↔ `cube_standard_summary`).
2. Mirrors `get_strand_rollup_for_item` in
   `backend/app/repositories/cube_repository.py` lines 257–307 but
   *without* the `WHERE qs.item_id = :item_id` filter — instead an
   optional `WHERE` block built from the filter params.
3. Computes `Grade_Average_Standard_Measure` per Strand as
   `AVG(cube_question_summary_overall.grade_average)` over all `ukey`
   rows in the strand. (NOT `AVG(cube_standard_summary.grade_average)` —
   the PBIX uses the question-overall cube, see DAX line 243 and
   existing `qso_avg` CTE in cube_repository.py line 290–294.)
4. Computes the secondary `standards_rollup` similarly via a new repo
   method `get_school_standard_rollup(filters)` mirroring
   `get_standard_rollup_for_item` lines 309–367.
5. Aggregates KPIs from the strands_rollup output (sum `num_standards`,
   sum `num_questions`, distinct `num_assessments`, plus
   `grade_average = avg over standards_rollup` to mirror SDD's KPI
   logic in `report_service.py` lines 348–358).
6. `total_students` from `cube_user_summary` (or `dim_student` count
   filtered to assessments matching the filters).
7. Stamps `perf_color` server-side using the same 70/80 thresholds:
   ```python
   def _perf_color(g: float) -> str:
       if g <= 0:        return ""
       if g < 0.7:       return "#FFCCFF"
       if g < 0.8:       return "#faff00"
       return "#00ff06"
   ```

> **Repo SQL sketch** (`get_school_strand_rollup`):
>
> ```sql
> WITH filtered_items AS (
>     SELECT DISTINCT di.item_id
>     FROM dim_item di
>     LEFT JOIN dim_subject dsubj
>       ON dsubj.school_id = di.school_id AND dsubj.subject_id = di.subject_id
>     LEFT JOIN dim_section dsec
>       ON dsec.school_id = di.school_id AND dsec.item_id = di.item_id
>     WHERE (:session  IS NULL OR dsubj.session = :session)
>       AND (:subject  IS NULL OR dsubj.subject = :subject)
>       AND (:grade    IS NULL OR dsubj.grade   = :grade)
>       AND (:category IS NULL OR dsubj.assessment_type = :category)
>       AND (:section  IS NULL OR dsec.section_name = :section
>                              OR dsec.section_code = :section
>                              OR dsec.section_nid  = :section)
> ),
> strand_q AS (
>     SELECT DISTINCT
>         ds.strand, ds.strand_id, qs.ukey, qs.identifier, qs.item_id
>     FROM cube_question_summary qs
>     JOIN dim_strand ds ON ds.identifier = qs.identifier
>     JOIN filtered_items fi ON fi.item_id = qs.item_id
>     WHERE ds.strand IS NOT NULL AND ds.strand <> ''
> ),
> qso_avg AS (
>     SELECT ukey, AVG(grade_average) AS grade_average
>     FROM cube_question_summary_overall
>     GROUP BY ukey
> )
> SELECT
>     sq.strand,
>     COUNT(DISTINCT sq.identifier)               AS num_standards,
>     COUNT(DISTINCT sq.ukey)                     AS num_questions,
>     COUNT(DISTINCT sq.item_id)                  AS num_assessments,
>     AVG(COALESCE(qa.grade_average, 0))          AS grade_average
> FROM strand_q sq
> LEFT JOIN qso_avg qa ON qa.ukey = sq.ukey
> GROUP BY sq.strand
> ORDER BY sq.strand
> ```

### Frontend (Next.js + shadcn + Recharts)

**Page route:** `frontend/src/app/app/reports/strand-summary/page.tsx`
(school-wide; no `item_id` query param required).

**Add to `reports-nav.tsx`** (`frontend/src/components/app/modules/reports/reports-nav.tsx`):

```typescript
{
  name: 'Strand Summary',
  href: '/app/reports/strand-summary',
  icon: Layers,        // or `Grid3x3` to differentiate from SDD
  requiresItem: false, // ← school-wide
},
```

**Add to `reportsApi`** (`frontend/src/lib/services/reports-service.ts`):

```typescript
strandSummary: async (filters: StrandSummaryFilters) => {
  const params = new URLSearchParams(
    Object.entries(filters).filter(([, v]) => v) as [string, string][]
  );
  const r = await fetch(`/api/v1/reports/strand-summary?${params}`);
  if (!r.ok) throw new Error(`Strand Summary fetch failed: ${r.status}`);
  return r.json() as Promise<StrandSummaryPayload>;
},
```

And `reportsKeys.strandSummary(filters)`.

**Add types to `frontend/src/lib/reports/types.ts`** mirroring the
Pydantic shape above.

**Page composition:**

| PBIX visual / area | React component | Notes |
|---|---|---|
| Header (Subject + Grade banner + Strand banner #6) | `<ReportPageHeader title="Strand Summary" subtitle={…current filter chips…} />` | Re-use existing shared header; bind to filter state. |
| Filter bar (NEW — replaces the missing PBIX slicer) | `<ReportFilters value={filters} onChange={setFilters} />` | Re-use existing component; default = no filter. |
| KPI strip (NEW — upgrade from PBIX text-only echoes) | `<StrandSummaryKpiStrip kpis={data.kpis} />` | New component in `frontend/src/components/app/modules/reports/strand-summary/`. Cards: Strands, Standards, Questions, Assessments, Students, Grade Average. Re-use `<KpiCard>`. |
| Bar chart #0 (Incorrect % by Strand) | `<StrandIncorrectBars strands={data.strands_rollup} />` | Recharts horizontal `<BarChart>`, `dataKey="incorrect_pct"`, `<Cell fill={1-grade_avg → trafficLight}>` (use `performanceColor()` in colors.ts). Sort desc. Y-axis = strand name. |
| Column chart #10 (Correct % by Strand) | `<StrandCorrectColumns strands={data.strands_rollup} />` | Recharts vertical `<BarChart>` (Recharts uses BarChart for both orientations; set `layout="horizontal"`). `dataKey="grade_average"`, `<Cell fill={performanceColor(grade_avg)}>`. Sort desc. |
| Mini pair (#17 + #18) | **omit** in school-wide rebuild — they duplicate the two charts above, and the small 320×240 tile constraint that motivated them doesn't apply to our 1280-wide canvas. | |
| Strand-rollup table | `<StrandRollupTable strands={data.strands_rollup} />` | New component. Table cols: Strand, # Standards, # Questions, # Assessments, Grade Average %, Performance (color pill). Mirror existing `<StrandsRollupTable>` from sdd/StandardsTable.tsx (ref `frontend/src/components/app/modules/reports/sdd/StandardsTable.tsx`). |
| Per-Standard drill-down (the PBIX shows it via the per-tile context; our rebuild surfaces it as a table below the strand rollup) | `<StrandStandardsTable standards={data.standards_rollup} />` | Group rows by strand; each row = (cpalms_standard, # questions, # assessments, grade_avg, color pill). Re-use `<StandardsRollupTable>` patterns from sdd/StandardsTable.tsx. |
| Cluster / Cognitive Complexity strip (#20–#23) | **drop** — not meaningful at strand-grain. | |
| Footer date | `<ReportDataTimestamp />` (small text bottom-right) | Optional; can pull from `MAX(dim_standard.lastChangeDateTime)` or simply omit. |

**Page skeleton:**

```typescript
'use client';

import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import StrandSummaryKpiStrip from '@/components/app/modules/reports/strand-summary/KpiStrip';
import StrandIncorrectBars from '@/components/app/modules/reports/strand-summary/StrandIncorrectBars';
import StrandCorrectColumns from '@/components/app/modules/reports/strand-summary/StrandCorrectColumns';
import StrandRollupTable from '@/components/app/modules/reports/strand-summary/StrandRollupTable';
import StrandStandardsTable from '@/components/app/modules/reports/strand-summary/StrandStandardsTable';

export default function StrandSummaryPage() {
  const [filters, setFilters] = useState({});
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.strandSummary(filters),
    queryFn: () => reportsApi.strandSummary(filters),
  });

  if (isLoading) return <LoadingState label="Loading Strand Summary…" />;
  if (isError) return <ErrorState message={…} onRetry={() => void refetch()} />;
  if (!data) return null;

  return (
    <ReportCanvas>
      <ReportPageHeader title="Strand Summary" subtitle="School-wide strand performance across all assessments" />
      <ReportFilters value={filters} onChange={setFilters} />
      <StrandSummaryKpiStrip kpis={data.kpis} />
      <div className="grid grid-cols-2 gap-2">
        <StrandCorrectColumns strands={data.strands_rollup} />
        <StrandIncorrectBars strands={data.strands_rollup} />
      </div>
      <StrandRollupTable strands={data.strands_rollup} />
      <StrandStandardsTable standards={data.standards_rollup} />
    </ReportCanvas>
  );
}
```

### Color tokens

Re-use the existing exports from
`frontend/src/lib/reports/colors.ts` — they're already PBIX-mandated:

```typescript
import {
  PERF_PINK,           // '#FFCCFF'
  PERF_YELLOW,         // 'yellow'  (PBIX uses '#FFFF00' or '#faff00')
  PERF_GREEN,          // '#00FF06'
  INCORRECT_GREY,      // '#CCCCCC'
  HEADER_BAR_BG,       // '#B8DBFF' (PBIX section header bars)
  KPI_CARD_BG,         // '#B8DBFF'
  LAYOUT_BORDER,       // '#B3B3B3'
  GRID_LINE,           // '#E5E5E5'
  performanceColor,    // (g) → PERF_PINK | PERF_YELLOW | PERF_GREEN
} from '@/lib/reports/colors';
```

> **Optional fidelity bump:** the PBIX yellow inside the Strand Summary
> visuals is `'#faff00'` (line 254/352/420) not `'#FFFF00'`. Visually
> identical at 1.7-degree hue shift. Our existing `PERF_YELLOW = 'yellow'`
> constant is fine — keep consistent with other reports rather than
> introduce a per-page yellow.

### Final canvas geometry (1280-wide breakpoint, suggestion)

```
Page header (filters + title):   y=0…64
KPI strip (6 cards):              y=64…160
Correct columns | Incorrect bars: y=160…480 (2-col grid, ~320 px tall each)
Strand rollup table:              y=480…700 (one row per strand)
Standards rollup table:           y=700…end (one row per (strand, standard))
```

Mobile responsive: stack the two charts vertically; tables scroll
horizontally if needed.

---

## §9 Cross-references

| What | Where |
|------|-------|
| Page object & visual JSON | `_layout.full.json` lines 245–492 |
| Visual list (markdown) | `20_pages.md` lines 57–115 |
| Visual list (JSON) | `20_pages.json` lines 277–586 |
| Per-page field map | `22_fields_per_page.json` lines 51–103 |
| DAX `Grade_Average_Standard_Measure` | `04_dax_measures.dax` lines 215–243 |
| DAX `Incorrect_Grade_Average_Standard_Measure` | `04_dax_measures.dax` lines 551–569 |
| DAX `Performance Color Strand` | `04_dax_measures.dax` lines 181–197 |
| DAX `Performance Color Standard2` | `04_dax_measures.dax` lines 1043–1056 |
| DAX `Total Standard` | `04_dax_measures.dax` lines 159–162 |
| DAX `Total Question Strand` | `04_dax_measures.dax` lines 405–425 |
| DAX `Total Question Standard` | `04_dax_measures.dax` lines 371–398 |
| DAX `Total Standard by Strand` | `04_dax_measures.dax` lines 432–440 |
| Power Query `dim_strand` | `07_power_query.m` lines 76–83 |
| Power Query `dim_standard` | `07_power_query.m` lines 116–126 |
| Power Query `cube_question_summary_overall` | `07_power_query.m` lines 161–173 |
| Cube schema (`cube_standard_summary`, `dim_strand`) | REPORT.md §3.1, §3.3 lines 67–93 |
| Companion analysis | REPORT.md §6 lines 233–254 (page table); 52_third_report_options.md lines 14–15 |
| Existing repo strand rollup (per-item) | `backend/app/repositories/cube_repository.py` lines 257–307 (`get_strand_rollup_for_item`), lines 309–367 (`get_standard_rollup_for_item`), lines 225–251 (school-wide `get_strand_rollup` — exists but joins `cube_standard_summary` directly; we'll add a sibling that respects the filter params via `dim_subject` join) |
| Existing report service | `backend/app/services/report_service.py` lines 321–400 (`build_standards_deep_dive`) — closest analogue |
| Existing colors | `frontend/src/lib/reports/colors.ts` (full file) |
| Existing strand visualisation | `frontend/src/components/app/modules/reports/sdd/StrandTreemap.tsx` (treemap, can reuse the `performanceColor()` and `truncate` helpers) |
| Existing band-bar (3 panels for SDD) | `frontend/src/components/app/modules/reports/sdd/CorrectIncorrectBars.tsx` — pattern to crib for our `<StrandCorrectColumns>` / `<StrandIncorrectBars>` |
| Existing strand rollup table | `frontend/src/components/app/modules/reports/sdd/StandardsTable.tsx` (both `<StrandsRollupTable>` and `<StandardsRollupTable>`) — direct pattern reuse |
| Existing report nav | `frontend/src/components/app/modules/reports/reports-nav.tsx` — add Strand Summary entry |
| Existing filter bar | `frontend/src/components/app/modules/reports/shared/ReportFilters.tsx` |
| Existing report page wrapper | `frontend/src/components/app/modules/reports/shared/ReportCanvas.tsx`, `ReportPageHeader.tsx` |
| Companion SDD spec | `data/_pbix_extract/50_sdd_spec.md` (this spec mirrors its structure) |

---

*Generated 2026-05-15 from `data/Assessment Analysis Dashboard.pbix`
extract files. Re-derive page details by reading
`_layout.full.json` lines 245–492 (the entire Strand Summary page
object).*
