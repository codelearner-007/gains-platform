# Question Response Analysis — Spec & Gap Analysis

> Compares the two PBIX pages named "Question Response Analysis" against
> what we have built in `frontend/src/app/app/reports/question-response-analysis/`.
> Sources: `20_pages.json`, `22_fields_per_page.json`, `30_qra_interactive.json`,
> `04_dax_measures.dax`, and the live frontend/backend code.

---

## §1. The two PBIX pages compared

The PBIX contains **two** distinct pages whose names both begin with
"Question Response Analysis":

| Aspect | Page #9 — `Question Response Analysis` | Page #17 — `Question Response Analysis Interactive` |
|---|---|---|
| Visual count | **8** | **28** |
| Rendering paradigm | Paginated/print (one PDF page per assessment) | Interactive dashboard (slicers/cross-filter) |
| Big "table" of questions | **Embedded `rdlVisual`** (an SSRS/RDL paginated report layout that renders the per-question table). All 8 columns — No, Question, % Correct, Correct Answer, Incorrect Choice Details, Incorrect Details Name, Standards, Description — live inside that single RDL container. | Native Power BI `tableEx` over `cube_question_summary_overall` with the 8 DAX-driven measures (`questionDax`, `__FirstFormatted_correct_`, `__FirstFormatted_Incorrect_Choice_Details`, `__FirstFormatted_Incorrect_Details_Name`, `CombineStandardsColumn`, `CombineDescriptionsColumn`, `Sorting Question_No`, `Grade_Average`). |
| KPI strip | One `multiRowCard` (Total Questions / Total Students / Score / Points Possible / % Correct) | Six standalone `card` visuals (Total Students, Number of Questions, Number of Standards, Grade Average, Overall Highest %, Overall Lowest %) plus a `card` for Instructor(s) |
| Header H1/H2/H3 | `Titles.H1 - Longitudinal`, `Titles.H2 Course and Unit`, `Titles.H2 - Assessment Type` (3 multiRowCards stacked vertically) | Same titles + a `card` "Instructor(s):" + the 6 KPI cards |
| Strands & Standards summary tables | **Not present** — that view is unique to QRA Interactive | Two `tableEx` panes: "Correct % by Strands" (dim_standard.Strand × Total Standard × Grade_Average_Standard_Measure) and "Correct % by Standards" (cube_question_summary_overall.Standards × Total Question Standard × Grade_Average_Standard_Measure), both with `Performance Color Standard` cell shading |
| Charts | None | `barChart` "Correct … by Standards", `clusteredBarChart` "Incorrect Choice", `hundredPercentStackedBarChart` "Correct and Incorrect %", `treemap` "Total Questions by Short Strand × Standard", `funnel` "Standards by # of Questions" |
| Slicer | None — output is per-Item PDF rendered with the M `SchoolID`/`Item_ID` parameter | One `slicer` over `Standards.Short Strand` (cross-filters every body visual on that page) |
| Action buttons / chrome | One `actionButton` (used as Back/Reset hyperlink), school logo image | Two `actionButton`s, school logo image, vertical line `basicShape`, two textboxes, two custom-visual placeholders (`d8767445…`, `467d134…`) |
| Source tables | `Titles`, `Key Measures`, `Student Submissions`, `dim_item`, `dim_subject`, `cube_question_summary_overall`, `SchoolLogo_Parameter` | Same set **plus** `Measure`, `dim_standard`, `Standards` (== `dim_standard` alias), `Questions Data` (== `cube_question_summary_overall` alias) |
| Filters | `dim_item.Item_ID` page-level filter (drills in from Home) | Page-level filter on Subject/Item still applies, but slicer + treemap-click change scope client-side |
| User journey | Linked **from** Year-To-Date drill-through; rendered as static PDF per assessment | Standalone exploratory view; the user changes Standard slicer / clicks treemap to refilter the question table |

### Verdict on the screenshot the user previously approved
The screenshot you matched against — the layout that has **(a)** a single "Instructor(s):" card on the left, **(b)** a 6-KPI strip across the top, **(c)** the "Summary by Standards" header with two side-by-side tables (Strands + Standards), and **(d)** the long question detail table — is **structurally the QRA Interactive page minus the charts/treemap/slicer**. It is *not* the paginated 8-visual Page #9. Page #9 has neither the 6 KPI cards nor the Strand/Standard summary tables; those features only appear on Page #17.

In other words: the implementation in `frontend/src/app/app/reports/question-response-analysis/page.tsx` is a **Page #17 layout, with the chart row deliberately omitted**. That is what the user approved.

---

## §2. Our current implementation walkthrough

`frontend/src/app/app/reports/question-response-analysis/page.tsx`:

```
URL  → /app/reports/question-response-analysis?item_id=<uuid>
       ↓
Page reads item_id from URL, redirects to /app/reports if missing.
       ↓
useQuery → reportsApi.qra(itemId) → fetch('/api/v1/reports/question-response-analysis/<id>', credentials:'include')
       ↓ Next.js rewrites → FastAPI
       ↓
FastAPI router (backend/app/api/v1/reports.py) → ReportService.build_question_response_analysis(item_id)
       ↓
ReportService composes 6 cube/dim queries → CubeRepository methods:
   - get_assessment_meta(item_id)               // dim_item + dim_subject
   - get_school_summary_for_item(item_id)       // cube_school_summary
   - get_grade_summary_for_item(item_id)        // cube_grade_summary
   - get_questions_overall_for_item(item_id)    // cube_question_summary_overall
   - get_incorrect_choices_for_item(item_id)    // cube_questionincorrectchoice_summary
   - get_students_for_item(item_id)             // dim/raw student lookup
   - get_raw_question_options_for_item(item_id) // raw question_data
       ↓
QuestionResponseAnalysisPayload returned (assessment, kpis, students, questions_overall, incorrect_choices, raw_question_options)
```

### Visuals currently rendered (PBIX → React component map)

| # | Component | Renders | Maps to PBIX visual on Page #17 (Interactive) |
|---|---|---|---|
| 1 | `PageHeader` | School logo + "Question Response Analysis" + Grade/Item subtitle + assessment-type | Combines Page #17's `simpleImage` (logo) + `multiRowCard` H2 Course-and-Unit + H2 Assessment-Type + textbox "Question Response Analysis" |
| 2 | `InstructorCard` | "Instructor(s):" label + names list (one per line) | `card` titled "Instructor(s):" using `Titles.Instructor(s):` |
| 3 | `KpiStrip` (6 cards) | Total Students, # Questions, # Standards, Grade Average, Overall Highest %, Overall Lowest % | Six `card` visuals (Measure.Total Student / Total Question / Total Standard / Grade_Average_Standard_Measure / Grade Max / Grade Min) |
| 4 | `SummaryByStandardsHeader` | Blue bar with text "Summary by Standards" | Equivalent to the textbox "Summary by Standards" on Page #17 |
| 5 | `StrandsTable` | Strand × # Standards × % per Strand, with cellColor on the percent | `tableEx` titled "  Correct % by Strands" (dim_standard.Strand × Measure.Total Standard × Grade_Average_Standard_Measure) |
| 6 | `StandardsTable` | Standards × # Questions × % per Standard | `tableEx` titled "  Correct % by Standards" (cube_question_summary_overall.Standards × Measure.Total Question Standard × Grade_Average_Standard_Measure) |
| 7 | `QuestionDetailTable` | No / Question / % Correct / Correct Answer / Incorrect Choice Details / Incorrect Details Name / Standards | `tableEx` (the 8-column one bound to `cube_question_summary_overall` with all the `__FirstFormatted_*` measures) |

We have **7 React components covering 7+ of the Page #17 visuals**, with the other 21 visuals (slicer, treemap, funnel, 3 bar-chart variants, action buttons, decorative shapes/textboxes, the 2 unknown custom visuals) **deliberately not built**.

### Performance-color thresholds
`frontend/src/lib/reports/colors.ts` matches the PBIX exactly: `< 0.7 → pink/transparent`, `0.7–0.8 → yellow`, `≥ 0.8 → #00FF06`. Note the deliberate divergence: `cellColor()` returns `transparent` instead of pink under 0.7, which is what the user approved against the screenshot. `performanceColor()` retains the canonical `#FFCCFF` if we ever need it.

---

## §3. Static dependency audit

### `frontend/src/lib/pilot/` — not present
```
> Glob frontend/src/lib/pilot/**  → No files found
```
The old static-dataset directory referenced in the backend docstrings (`frontend/src/lib/pilot/dataset.ts`) **no longer exists**. The contract has moved to `frontend/src/lib/reports/types.ts`.

### Live `pilot` references in the repo

```
backend/app/middleware/rls.py:25                 // comment: "Athenian fallback so the pilot page is unblocked."
backend/app/jobs/parsers/question_data.py:58     // comment only
backend/app/jobs/parsers/common.py:35            // comment only
backend/app/schemas/reports.py:3,4               // doc-comment referencing old dataset.ts contract
backend/app/services/report_service.py:4,5       // doc-comment referencing old dataset.ts contract
frontend/src/components/app/modules/reports/qra/PageHeader.tsx:19   // src="/pilot/athenian-logo.png"
frontend/src/components/app/modules/reports/qra/QuestionDetailTable.tsx:107  // className="pilot-question-html" (CSS hook only)
```

**Real runtime dependencies on `pilot/`:** exactly one — the school-logo image at
`frontend/public/pilot/athenian-logo.png`, hardcoded in `PageHeader.tsx`.

```ts
<Image src="/pilot/athenian-logo.png" alt={assessment.school_name || 'School'} … />
```

This is a **static asset path**, not a static data fallback, but it ties the
component to one specific school. In the PBIX this is the `SchoolLogo`
parameter (per-tenant). For multi-tenant correctness it should come from
`assessment.school_logo_url` (which the backend doesn't yet emit).

The other matches are docstrings / a CSS class name (`pilot-question-html`) and
do not load any data.

### Hardcoded data fallbacks
Searched `frontend/src/app/app/reports` for `dataset|hardcoded|gains/` — **no
matches**. There is no static `dataset.ts` import anywhere on the QRA path.

The `StrandsTable` and `StandardsTable` components contain a sentinel "fallback"
row when the `strands` / `standards` props are `undefined`, but those props are
**never populated by the current backend** — see §7 — so the fallback is what
the user actually sees. This is the only "stand-in data" in the QRA path, and
it is a render-time placeholder, not a data import.

---

## §4. Gap analysis

### Things on Page #17 (Interactive) we don't have
- **Slicer** on `Standards.Short Strand` — would let the user filter every visual on the page by selecting one or more strands. We don't expose `short_strand` in the payload at all.
- **Treemap** (`Total Questions` grouped by `Short Strand` → `Standard`, coloured by `% Correct` traffic-light) — needs a per-(strand,standard) aggregation in the API.
- **Funnel** chart "Standards by # of Questions" — single-dimension, easy to add once Standards rollup ships.
- **`hundredPercentStackedBarChart` "Correct and Incorrect % by Standards"** — same data as the Standards table but stacked.
- **`barChart` + `clusteredBarChart`** "Correct/Incorrect % by Standards" — duplicate views of the same Standards data; PBIX uses three different chart types side-by-side because the report author wanted alternates, not because they show different data.
- **Strands & Standards summary tables**: **Superseded 2026-05-18.** Backend now populates `strands_rollup`/`standards_rollup`. See `.hermes/report-parity/RCA-2026-05-18-consolidated.md` for the current data-wire defects and `.hermes/report-parity/PLAN-2026-05-18-implementation.md` for the fix path.
- **`Performance Color Standard` cell tint on the strand/standard tables**: works because we use `cellColor()`, but the color swap from `transparent` → `#FFCCFF` is intentional; flag for the user.
- **Description column** on the question detail table: schema has `description` (`CombineDescriptionsColumn`) but the table doesn't show it. PBIX Page #17's table includes it as the rightmost column.
- **Question's `position_number`** (the "1: A, 2: B, 3: C" sub-question splitter): payload carries it; component uses `formatCorrectAnswer` to break by comma but ignores `position_number`. The DAX `__FirstFormatted_correct_` actually concatenates `Position_Number & ': ' & Correct_Answer`. Minor but not faithful.
- **Two action buttons** (back / reset slicer) and the **vertical separator line**.
- **Two custom visual containers** (`d8767445735262b0b0c0`, `467d134060d51b7cae0e`) — these are unknown custom-visual GUIDs in the PBIX. Unused as far as the field bindings show; safe to drop.
- **School logo from per-tenant data** — currently hardcoded to `/pilot/athenian-logo.png`.

### Things on Page #9 (paginated) we don't have
- The whole page is an `rdlVisual` plus a 5-measure `multiRowCard` — its "all questions in one table" rendering is what the user wanted, and we already have that table. The layout is otherwise a **subset** of Page #17. Nothing on Page #9 is missing from our implementation that isn't also on Page #17.

---

## §5. Recommendation: keep the simpler page or upgrade to Interactive?

**Recommendation: keep the current "Page #17 minus charts" layout, fix the data gaps, and defer the chart row + slicer to a later iteration.**

Reasoning:
1. **The user already approved this layout.** The screenshot review they signed off matched the current rendering (header + InstructorCard + 6 KPIs + summary tables + question table). Re-litigating the layout now will cost more cycles than it saves.
2. **The charts on Page #17 are redundant viewing modes.** The bar chart, clustered bar chart, and 100%-stacked bar chart all show the **same Standards × % Correct data** the StandardsTable already shows, just as bars. The PBIX author left three of them in because Power BI makes that easy; they are not separate insights.
3. **The slicer changes the report's meaning.** With a slicer the page becomes "explore one strand at a time"; without it the page is "single-page assessment summary, scannable like a PDF." The latter is closer to what teachers ask for in Athenian's existing PDF workflow, which is the use case the user has been validating against.
4. **The treemap and funnel duplicate Standards info too.** Treemap groups `# Questions` by Strand→Standard; funnel ranks Standards by `# Questions`. Both are derivable from data we'll already have once `strands` / `standards` are wired into the payload.
5. **The two missing data wires** (StrandsTable.strands, StandardsTable.standards) are the actual blockers for "100% faithful to the screenshot." Those should ship before any new visual is added.
6. **Performance**: building the slicer + 5 chart components + the treemap is roughly 5–8 days of frontend work; the data-wire fix is < 1 day. Ship the cheap fix first.

If the user decides at review time that "Interactive" must include charts, treat that as a follow-up (see §6). Otherwise the right next step is §7.

---

## §6. If we DO upgrade to Interactive — components/visuals to build

(Order: data first, then UI. All charts read from the same expanded payload.)

### Backend (FastAPI / ReportService)
1. **Extend `QuestionResponseAnalysisPayload`** with two new arrays:
   - `strands: StrandRollupRow[]` — per-strand, scoped to this `item_id` (NEW; today the strand rollup endpoint is global).
   - `standards: StandardSummaryRow[]` — per-standard, scoped to this `item_id`.
2. **New repository methods** (`CubeRepository`):
   - `get_strand_rollup_for_item(item_id)` — group `cube_standard_summary` by `strand_id` filtered by `item_id`.
   - `get_standards_for_item(item_id)` — `cube_standard_summary` filtered by `item_id`, joined to `dim_standard` for `schoology_standard` / `description` / `short_strand`.
3. Add `school_logo_url` to `AssessmentMeta` (read from `dim_item` / per-tenant `schools` row).

### Frontend
4. **`QraSlicer`** — multi-select pill list bound to `Short Strand`; lifted state filters StrandsTable, StandardsTable, treemap, funnel, charts, and (page-level) the question table.
5. **`StandardsTreemap`** (`recharts <Treemap />`) — groups by `short_strand` then `standard`, value = `total_questions`, fill via `performanceColor(grade_average)`.
6. **`StandardsFunnel`** (`recharts <FunnelChart />`) — single funnel of standards by `# questions`.
7. **`StandardsBarChart`** (`recharts <BarChart layout="vertical">`) — `% of Correct Answers` per Standard, fill via `performanceColor`. Pair with a clustered variant showing `% of Incorrect Choice` for distractor-strength comparison.
8. **`StandardsStackedBar`** (`recharts <BarChart stackOffset="expand">`) — Correct vs Incorrect 100%-stacked.
9. **`SchoolLogo`** component reading `assessment.school_logo_url` (replace the hardcoded `/pilot/athenian-logo.png`).
10. **`QuestionDetailTable.Description` column** — render `CombineDescriptionsColumn` (already in payload as `description`).
11. **Two `ActionButton`s** — Back (push to `/app/reports`) and Reset (clear slicer state).

### Optional polish
12. Replicate `__FirstFormatted_correct_` with `Position_Number`, e.g. `"1: A\n2: B\n3: C"`, by joining `position_number` and `correct_answer` arrays in the API rather than splitting on comma in the UI.
13. Add the vertical separator and "Question Summary Report" textbox so the layout matches pixel-for-pixel.

---

## §7. If we DON'T upgrade — polish list to make the simpler page truly faithful

These are the cheapest items that close the visible gaps the user is most likely to notice on the page they have already approved.

1. **Wire the Strands & Standards tables to real data.** Today both tables receive an undefined prop and render the fallback row.
   - Backend: add `strands` and `standards` to `QuestionResponseAnalysisPayload` (per-item, scoped — see §6 step 1).
   - Frontend: pass them through from `page.tsx` (`<StrandsTable kpis={data.kpis} strands={data.strands} />`, similar for standards).
2. **Pull the school logo from the assessment.**
   - Backend: include `school_logo_url` in `AssessmentMeta`. For Athenian (single tenant today) it can resolve to the same `/pilot/athenian-logo.png` or, better, an absolute Supabase Storage URL keyed by `school_id`.
   - Frontend: `<Image src={assessment.school_logo_url || '/pilot/athenian-logo.png'} … />`.
3. **Render `position_number` in the Correct Answer column.** Replace `formatCorrectAnswer(q.correct_answer)` with a helper that zips `position_number` and `correct_answer` so multi-part questions display "1: A / 2: C" rather than "A, C".
4. **Show the Description text under each question** (the PBIX includes it as a wrapped paragraph below the standards label). Payload already carries `description`.
5. **Make the % Correct column shade pink under 0.7** (currently `transparent`). Confirm with user — this is the only deliberate divergence from the PBIX traffic-light spec.
6. **Strip the doc-comments** that reference `frontend/src/lib/pilot/dataset.ts` from `backend/app/services/report_service.py` and `backend/app/schemas/reports.py` so future readers aren't pointed at a deleted file.
7. **Consider folding the "Summary by Standards" header into a real section heading** (semantic `<h2>`) for accessibility.
8. **Document the divergence** in a code comment on `colors.ts` so the next person knows the cell-color whitelist is intentional.

None of items 1–8 introduces new visuals; they only make the page render the data it claims to render and remove the last user-visible "pilot" string. Total effort estimate: 1–2 days.

---

## Quick contract reminders

- Frontend never imports Supabase or hits `localhost:8000`. The QRA path uses `/api/v1/reports/...` and Next.js rewrites it to FastAPI. Verified.
- Backend uses repository pattern (`Router → Service → Repository`). Verified in `reports.py` / `report_service.py` / `cube_repository.py`.
- `?item_id=X` is read by `useSearchParams()`, passed to `reportsApi.qra(itemId)`, which becomes the URL path parameter `/api/v1/reports/question-response-analysis/{item_id}`. The FastAPI route binds `item_id: str`, the service calls `get_assessment_meta(item_id)` (raises 404 if missing), then 5 more repo queries scoped by `item_id`. Zero static fallbacks on the data path. The only static fallback in the **render** path is the `/pilot/athenian-logo.png` image and the empty Strands/Standards rendering (item 1 above).
