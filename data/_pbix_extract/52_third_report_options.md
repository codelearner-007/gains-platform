# Third Pilot Report — Options & Recommendation

> Read-only research. Goal: pick the BEST third report to build on top of QRA + SDD.
> Constraint: must be visually richer than the first two (more charts, new chart types), use cubes already populated for Athenian, and ship in 1 day of frontend work.

---

## 1. Candidates Compared

| # | Page | Visual count | Visual types in PBIX | New chart types? | Data we have | 1-day fit | Verdict |
|---|---|---:|---|---|---|---|---|
| 1 | **Year To Date — Longitudinal** (3 variants) | 8 / 8 / 9 | `rdlVisual` (paginated SSRS), 4 `multiRowCard`, textbox, image, button | None natively — `rdlVisual` is a paginated PDF embed. **But the *concept* (YTD progression) lets us introduce line/area/scatter freely.** | Strong: `dim_item.assessment_date` (Apr 21–May 1, 6 dates), 33 items, 332 students, `cube_user_summary` (11.6k rows) with pre-computed per-item, per-section, per-overall, per-overall-year scores. | ✅ data is composition-only, frontend can be done in 1 day | **WINNER (re-imagined as interactive)** |
| 2 | Incorrect Answer Details | 17 | 3 `tableEx`, 1 `pivotTable`, 1 `treemap`, 6 `multiRowCard`, 1 card, image, shape, textbox, button | Pivot table + a treemap (we already have treemap on SDD) | `cube_questionincorrectchoice_summary` (2,877 rows) + `fact_student_submission` (16,075 rows) — fully populated | ✅ | Runner-up — but it's a drill-through page (per-question deep dive), so it's *narrower* than QRA, not broader |
| 3 | Standard Summary | 23 | 6 `multiRowCard`, 5 `card`, 4 `basicShape`, 2 textbox, 1 `barChart`, 1 `clusteredBarChart`, 3 custom-vendor visuals | Same chart family as QRA/SDD (just bars + cards) | `cube_standard_summary` (110 rows) + `dim_standard` (7,958 rows) — populated | ✅ | Skip — visually it's "yet another bar chart + tables", duplicates SDD |
| 4 | Strand Summary | 24 | 2 `barChart`, 2 `columnChart`, 1 `clusteredBarChart`, 7 `multiRowCard`, 3 `card`, 3 `basicShape`, custom vendor visuals | Adds vertical column chart vs horizontal bar — minor | `dim_strand` (24 rows) + `cube_standard_summary` | ✅ | Skip — same family as SDD |
| 5 | Question Summary Report (+ teacher subtotal, header highlights) | 8 / 8 / 9 | `rdlVisual` paginated only — **no native chart in the layout** | None | Same as QRA | ✅ | Skip — duplicate of QRA in different formatting |
| 6 | Question Response Analysis Interactive | 28 | bar, clustered bar, 100% stacked bar, treemap, funnel, slicer, tableEx, multiRowCard | We already built this | n/a | n/a | already shipped |
| 7 | Standards Deep Dive Interactive | 39 | bar, clustered bar, 3× 100% stacked bar, treemap, 2× Charticulator custom, funnel | We already built this | n/a | n/a | already shipped |

### Key visual-inventory observation

- **The PBIX longitudinal pages embed an SSRS paginated PDF (`rdlVisual`)** — they are not interactive line charts in Power BI. The *content* is page-per-assessment listings. So in the rebuild we are **not bound** to copy that exact rendering; we should re-imagine "Year To Date Longitudinal" as the **interactive trend dashboard the original report wanted but couldn't build in PBIX**.
- The original report has **no line chart, no area chart, no scatter, no heatmap, no boxplot anywhere across all 20 pages**. This is a gap our rebuild can fill — and the user explicitly asked for it.

### Existing chart inventory in our app (after QRA + SDD)

- BarChart (horizontal), ClusteredBarChart, 100% StackedBar (planned), Treemap (Recharts), KPI cards, tables. **No time-series, no scatter, no area, no heatmap.**

---

## 2. Top Recommendation — "Year To Date Performance" (re-imagined as interactive)

**Pitch:** A school-wide trend dashboard answering *"how are we doing across all assessments this year?"* — the cross-assessment, longitudinal view that QRA (per-question) and SDD (per-standard) deliberately don't provide.

### Why it wins

1. **Chart variety (the core ask).** Introduces FOUR new chart types in one page: line chart (time-series), stacked area (subject mix), scatter plot (assessment difficulty vs participation), and heatmap (grade × subject performance). All four are net-new for our app.
2. **Data we already have, no new SQL.**
   - `dim_item.assessment_date` — 6 distinct dates, 11-day window. Short, but **enough datapoints (22 date × item rows, 33 items)** to draw a meaningful line.
   - `cube_user_summary` (11,618 rows) carries pre-aggregated `total_score_by_item`, `total_score_by_overall`, `total_score_by_overall_year`, `total_score_by_section`, `total_score_by_standard` — a literal pre-computed YTD running total. It already does the heavy lifting; the PBIX itself relied on this exact column.
   - `cube_overallperformance_summary` (639 rows) for per-question / per-standard rollups.
   - `dim_subject` gives Grade × Subject for slicing; `dim_section` gives 28 sections for teacher-flavored views.
3. **Different lens from QRA + SDD.**
   - QRA = drill into ONE assessment's questions.
   - SDD = drill into standards/strands within ONE assessment.
   - **YTD = compare ACROSS assessments, ACROSS time, ACROSS grades/subjects.** Cross-cutting. This is exactly what an admin/principal opens first thing Monday morning.
4. **Teacher value.** A teacher can see whether her Grade-5 Math class is trending up or down across the 4 weekly quizzes; an admin can spot which grade or subject is dragging the school average; both can spot specific assessments that performed unusually low (outliers in scatter).
5. **1-day frontend fit.** Backend = 1 endpoint returning grouped time-series data (a single SQL query against `cube_user_summary` joined to `dim_item` and `dim_subject`). No new aggregations, no new tables. Frontend = compose 4 Recharts charts + reuse the existing `KpiStrip` + `PageHeader` + `ReportFilters` shells.
6. **PBIX-aligned.** The original report explicitly named a "Year To Date — Longitudinal" page. We're not inventing scope; we're delivering the modern interactive version of an existing page that the original couldn't render natively.

### Acknowledged limitation (and mitigation)

- Athenian's data is only an 11-day window with 1 session, 1 assessment type. **A pure year-over-year line is degenerate.** Mitigation: position the temporal axis as **"assessment sequence over the term window"** (date on x-axis, plus a dropdown to switch x to *Assessment # in sequence*). When more sessions/years arrive the same component renders longer trend lines without code change.

---

## 3. Runner-up — "Incorrect Answer Details" (drill-through page)

If the longitudinal idea is rejected (e.g., stakeholder wants a per-assessment, not cross-assessment, third report):

- 17 visuals, **drill-through from QRA**, deepens the "what did students get wrong and why" story.
- Adds **distractor frequency heatmap** (Question × Answer-option, color = % chose) — net-new chart type.
- Adds **pivot table** (a richer table than what we have).
- Reuses `cube_questionincorrectchoice_summary` (2,877 rows, fully populated).
- Cost: about the same 1-day budget as YTD.
- Drawback: it's narrower scope, and chart variety is lower (heatmap + pivot vs YTD's line + area + scatter + heatmap).

---

## 4. Implementation Plan — Year To Date Report

### 4.1 Backend (FastAPI) — single endpoint, ~80 LOC

**File:** `backend/app/api/v1/reports.py` (extend existing) and `backend/app/services/report_service.py`.

**Endpoint:** `GET /api/v1/reports/year-to-date?grade=&subject=&section_nid=`

**Returns:**
```json
{
  "kpis": {
    "total_assessments": 33,
    "total_students": 332,
    "ytd_grade_avg_pct": 0.79,
    "earliest_date": "2026-04-21",
    "latest_date": "2026-05-01"
  },
  "trend_by_date": [
    { "date": "2026-04-21", "students": 127, "ytd_avg": 0.83, "item_avg": 0.16 },
    { "date": "2026-04-22", "students": 95,  "ytd_avg": 0.86, "item_avg": 0.31 },
    ...
  ],
  "trend_by_assessment": [
    { "item_id": "...", "item_name": "Chapter 17", "date": "2026-04-22",
      "grade": "Grade 2", "subject": "Mathematics",
      "students": 57, "avg_pct": 0.398, "min_pct": 0.10, "max_pct": 0.95 }, ...
  ],
  "subject_mix_by_date": [
    { "date": "2026-04-21", "Mathematics": 0.07, "Science": 0.17, "Social Studies": 0.0, "Other": 0.25 }, ...
  ],
  "grade_subject_heatmap": [
    { "grade": "Grade 5", "subject": "Mathematics", "avg_pct": 0.067, "students": 38 }, ...
  ]
}
```

**Single SQL query** (one CTE per shape, no new aggregations — pure rollup of `cube_user_summary` joined to `dim_item` and `dim_subject`).

### 4.2 Frontend (Next.js + Recharts) — 1 page, 4 charts, ~400 LOC total

**Page:** `frontend/src/app/app/reports/year-to-date/page.tsx`

**Components (new, all in `frontend/src/components/app/modules/reports/ytd/`):**

| Component | Recharts primitive | Purpose |
|---|---|---|
| `PageHeader.tsx` | (none) | reuse pattern from QRA |
| `KpiStrip.tsx` | (none) | reuse pattern — 4 cards (Assessments, Students, YTD avg, Date range) |
| `YtdTrendLine.tsx` | `<LineChart>` with 2 lines (YTD running avg vs day's average) | **NEW chart type: line chart** |
| `SubjectMixArea.tsx` | `<AreaChart>` stacked, 4 subjects | **NEW: stacked area** |
| `AssessmentScatter.tsx` | `<ScatterChart>` x = participation count, y = avg %, color = grade, size = total points | **NEW: scatter** |
| `GradeSubjectHeatmap.tsx` | custom CSS grid, `lib/reports/colors.ts` thresholds | **NEW: heatmap (grade × subject)** |
| `AssessmentTimeline.tsx` | reuse pattern: small horizontal bar list grouped by date | leverages existing bar-chart skill |

**Service:** `frontend/src/lib/services/reports-service.ts` — add `getYearToDate(filters)`.

**Routing:** add to `reports-nav.tsx` as third tab.

### 4.3 Effort breakdown

| Task | Hours |
|---|---:|
| Backend SQL + service + endpoint + Pydantic schema | 1.5 |
| Frontend page + filters wiring | 0.5 |
| `YtdTrendLine` (LineChart) | 0.75 |
| `SubjectMixArea` (stacked Area) | 0.75 |
| `AssessmentScatter` (ScatterChart) | 1.0 |
| `GradeSubjectHeatmap` (CSS-grid) | 0.75 |
| `AssessmentTimeline` + `KpiStrip` + `PageHeader` reuse | 0.5 |
| Polish, loading/error states, responsive | 0.75 |
| **Total** | **~6.5 hr (within 1-day budget)** |

### 4.4 Risk register

- **Short date window (11 days, 6 dates).** Mitigation: x-axis can switch to "assessment sequence #" (1..33) so the line is always meaningful.
- **`dim_teacher` is empty.** Mitigation: use `cube_user_summary.section_nid` + `section_instructors` instead — no need for `dim_teacher`.
- **Recharts scatter sizing.** If Recharts is too constrained, fall back to a bubble-style `<ScatterChart><Scatter shape="circle" />` with manual radius — well-documented pattern.

---

## 5. New Chart Types Introduced

The existing app (after QRA + SDD) renders: bar chart, clustered bar, treemap, KPI cards, tables.

The YTD report adds:

| New chart | Recharts component | Used for | Visual style |
|---|---|---|---|
| **Line chart (time-series)** | `<LineChart>` + 2× `<Line>` | YTD running average vs day's average | shows trajectory |
| **Stacked area chart** | `<AreaChart>` + 4× `<Area stackId="a">` | Subject contribution to daily score | shows composition over time |
| **Scatter plot** | `<ScatterChart>` + `<Scatter>` with size + color | Assessments plotted by participation × difficulty | exposes outlier assessments |
| **Heatmap** | CSS grid + semantic Tailwind tokens (no Recharts needed) | Grade × Subject performance matrix | shows where the school is weak |

That's **four net-new chart types** in one report — the user will immediately *see* the visual richness step-up versus QRA + SDD, which were both bar-chart-and-table reports.

---

*Generated 2026-05-08. Source files: `data/_pbix_extract/REPORT.md`, `20_pages.json`, `22_fields_per_page.json`, live Postgres on port 56322 (cube_user_summary 11,618 rows, dim_item 33 items, 332 students, 6 distinct assessment dates).*
