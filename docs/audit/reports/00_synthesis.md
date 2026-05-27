# Six Paginated Reports — Implementation Synthesis

> Synthesised from three research passes:
> - `docs/audit/reports/question-summary.md` — Question Summary family (ord 6 / 7 / 16)
> - `docs/audit/reports/qra-paginated.md` — QRA paginated family (ord 11 / 12 / 13)
> - `docs/audit/reports/legacy-mapping.md` — legacy → current-platform mapping
>
> Read those three before touching the implementation. This synthesis only summarises decisions and the build plan.

---

## §0 Executive Summary

Six new "paginated" (PDF-style) reports must reach parity with the legacy Power BI / SSRS RDL output. All six are PBIX shells wrapping external RDL bodies hosted on Power BI Service workspace `8215049c-ebd6-4a9b-bb98-5b5fdb7d3da4`; the RDL XML is not in the repo, so cell-level structure was reverse-engineered from the rendered PDFs.

**Key facts:**

1. **Zero new cubes / cube columns required.** Every numeric the six reports need is already produced by `09_cubes/cube_question_summary.sql`, `cube_question_summary_overall.sql`, `cube_school_summary.sql`, `cube_questionincorrectchoice_summary.sql`, and `dim_question_data` ⋈ `dim_standard`.
2. **Two report families with different grains.**
   - QSR family (ord 6/7/16) — per-(student × question) **matrix**. Needs `fact_student_submission` joined to the question cube.
   - QRA paginated family (ord 11/12/13) — per-(question) or per-(teacher × question) or per-(standard × teacher × question) **list**.
3. **Three QSR variants collapse to one React component + one repo method** with two booleans (`show_teacher_subtotal`, `highlight_standard_header`).
4. **Three QRA paginated variants need three repo methods** because the SQL grain differs per variant (Agent B's grain analysis in `qra-paginated.md` §4 stands; Agent C's "one method serves all" claim is wrong for ord 12/13).
5. **Two new pieces of tenant config** need exposure on every paginated payload: `school_name` and `school_logo_url`.
6. **Pink-vs-transparent palette parity.** Paginated PDFs strictly use `#FFCCFF` for `<70%`. The current React `cellColor()` returns `transparent`. The paginated rebuilds must use the saturated PBIX palette (already declared as `PERF_PINK` etc. in `lib/reports/colors.ts`).

**Net cost beyond what already ships:** four new FastAPI endpoints, four new repository methods, four new React routes (QSR has one route with variant tabs; QRA paginated has three), shared chrome components, and a print-styled stylesheet (or `@react-pdf/renderer` opt-in for true PDF download).

---

## §1 Scope & route map

| # | PBIX page | Variant | New frontend route | New backend endpoint | Repo method |
|---|---|---|---|---|---|
| 1 | ord 6  | QSR — base | `/app/reports/question-summary-paginated/{itemId}` | `GET /api/v1/reports/question-summary-paginated/{item_id}` | `get_question_summary_matrix(item_id)` |
| 2 | ord 7  | QSR — teacher subtotal | same route + `?subtotal=teacher` | same endpoint + `?subtotal=teacher` | same method (`subtotal` is render-only) |
| 3 | ord 16 | QSR — header highlights | same route + `?highlight=true` | same endpoint + `?highlight=true` | same method (`highlight` is render-only) |
| 4 | ord 11 | QRA paginated — base | `/app/reports/question-response-analysis-paginated/{itemId}` | `GET /api/v1/reports/question-response-analysis-paginated/{item_id}` | `get_qra_paginated_for_item(item_id)` |
| 5 | ord 12 | QRA — by Teacher | `/app/reports/question-response-analysis-by-teacher/{itemId}` | `GET /api/v1/reports/question-response-analysis-by-teacher/{item_id}` | `get_qra_by_teacher_for_item(item_id)` |
| 6 | ord 13 | QRA — by Standard and Teacher | `/app/reports/question-response-analysis-by-standard-and-teacher/{itemId}` | `GET /api/v1/reports/question-response-analysis-by-standard-and-teacher/{item_id}` | `get_qra_by_standard_teacher_for_item(item_id)` |

**Why one QSR route with query params, three QRA routes:**
- QSR variants are pure presentation deltas on the same data matrix (subtotal rows, header coloring) — query params are cleaner than 3 routes.
- QRA paginated variants have **different payload shapes** — flat list (ord 11), `teacher_groups[]` (ord 12), `standard_groups[].teacher_groups[]` (ord 13). Casting unions in the frontend would be painful. Three endpoints, three repo methods, three React components.

**Out of scope (per user directive):** the three Year-To-Date Longitudinal reports (ord 8/9/10). The interactive QRA, SDD, and IAD already ship and are unchanged.

---

## §2 Data layer plan

### §2.1 Existing transformations — reuse as-is

| Cube / dim                                                | What we read                                                  |
|-----------------------------------------------------------|----------------------------------------------------------------|
| `cube_question_summary_overall`                           | Per-(question × standard × ukey) — header rows, KPI averages |
| `cube_question_summary`                                   | Per-(question × standard × section) — needed for QRA ord 12/13 grain |
| `cube_school_summary`                                     | KPI strip totals (`total_questions`, `total_students`, `total_score`, `total_possible_point`, `grade_average`) |
| `cube_questionincorrectchoice_summary`                    | Per-distractor (not directly used by QSR/QRA-paginated; KPI `Score` references `total_score` here but `cube_school_summary.total_score` is equivalent) |
| `dim_item`                                                | `item_name`, `assessment_date`, `section_instructors`         |
| `dim_subject`                                             | `assessment_type`, `grade`, `session`, `subject`              |
| `dim_question_data`                                       | `standard` (Schoology short form) — used by ord 11 detail rows |
| `dim_standard`                                            | `cpalms_standard` (long form) — used by ord 13 group headers  |
| `fact_student_submission`                                 | Per-(user × question) — drives the QSR matrix; drives ord 11 `Students with Incorrect Choice` |

**No new cube columns. No new migrations.**

### §2.2 New repository methods

All live in `backend/app/repositories/cube_repository.py`.

#### M1 — `get_question_summary_matrix(item_id)`

For the QSR family. Returns the per-(student × question) binary grid plus row/column totals.

**Output shape:**

```
{
  questions: [
    { question_id, question_no, sorting_question_no, standard, cpalms_standard, position_number, correct_answer }
    , …
  ],                       # ordered by (cpalms_standard ASC, sorting_question_no ASC)
  teacher_groups: [
    {
      section_instructor: str,
      teacher_score_pct: float,
      students: [
        {
          user_uid: str,
          user_name: str,
          score_pct: float,
          possible_points: int,
          correct_count: int,
          cells: { question_id: 0 | 1 | null }   # null = not attempted
        }
      ]                    # ordered ASC by score_pct
    }
  ],                       # ordered alphabetically by section_instructor
  grand_total: {
    possible_points: int,
    correct_count: int,
    score_pct: float,
    per_question_possible: { question_id: int },
    per_question_correct:  { question_id: int },
    per_question_pct:      { question_id: float },
  }
}
```

**SQL shape (one query):**

```sql
SELECT
  fss.user_uid, fss.user_name, fss.section_instructors,
  fss.question_id, fss.points_received, fss.points_possible,
  qso.question_no, qso.sorting_question_no, qso.standards,
  qso.position_number, qso.correct_answer,
  ds.cpalms_standard
FROM fact_student_submission fss
JOIN cube_question_summary_overall qso
  ON qso.question_id = fss.question_id AND qso.subject_id = fss.subject_id
LEFT JOIN dim_standard ds
  ON ds.schoology_standard = SPLIT_PART(qso.standards, E'\n', 1)
WHERE fss.item_id = :item_id
  AND fss.school_id = :school_id
ORDER BY fss.section_instructors, fss.user_name, qso.sorting_question_no
```

Pivot to the matrix shape in Python (≤ a few thousand rows per assessment).

#### M2 — `get_qra_paginated_for_item(item_id)` — ord 11

Per-question flat list with the new per-question `incorrect_students` array (named students per wrong answer).

Two queries:
1. The existing `get_questions_overall_for_item` shape (already exists at `cube_repository.py:278`).
2. NEW: `get_incorrect_choice_students_for_item(item_id)` —
   `SELECT question_id, answer_submission, ARRAY_AGG(user_name ORDER BY user_name) FROM fact_student_submission WHERE item_id = :item_id AND points_received <> '1' GROUP BY question_id, answer_submission`.

Merge by `question_id` in the service layer.

#### M3 — `get_qra_by_teacher_for_item(item_id)` — ord 12

Per-(section_instructor × question) grain. Read from `cube_question_summary` (which is per-section, not collapsed).

```sql
SELECT
  qs.section_instructors, qs.question_id, qs.question_no, qs.sorting_question_no,
  qs.question, qs.correct_answer, qs.position_number,
  qs.grade_average, qs.incorrect_choice_details
FROM cube_question_summary qs
WHERE qs.item_id = :item_id AND qs.school_id = :school_id
ORDER BY qs.section_instructors, qs.grade_average ASC, qs.sorting_question_no
```

Group by `section_instructors` in Python; emit `teacher_groups[]`.

#### M4 — `get_qra_by_standard_teacher_for_item(item_id)` — ord 13

Per-(cpalms_standard × section_instructor × question) grain, plus two roll-up aggregates.

```sql
SELECT
  ds.cpalms_standard,
  qs.section_instructors, qs.question_id, qs.question_no, qs.sorting_question_no,
  qs.question, qs.correct_answer, qs.position_number, qs.grade_average,
  qs.incorrect_choice_details,
  AVG(qs.grade_average) OVER (PARTITION BY ds.cpalms_standard, qs.section_instructors) AS teacher_standard_avg,
  AVG(qs.grade_average) OVER (PARTITION BY ds.cpalms_standard)                          AS standard_avg
FROM cube_question_summary qs
JOIN dim_question_data dqd USING (question_id)
JOIN dim_standard ds       ON ds.schoology_standard = dqd.standard
WHERE qs.item_id = :item_id AND qs.school_id = :school_id
ORDER BY ds.cpalms_standard, qs.section_instructors, qs.grade_average ASC
```

Group by `(cpalms_standard, section_instructor)` in Python; emit nested `standard_groups[].teacher_groups[].questions[]`.

### §2.3 Tenant config — two new strings on the assessment payload

`school_name` and `school_logo_url` live in PBIX parameters today (`07_power_query.m:187`, `:196`). On our platform they belong in the `schools` table.

**Decision required:** confirm whether a `school_logo_url` column already exists on `schools` (check during phase 0). If not, add one — small migration — and expose `school_name` + `school_logo_url` via the existing `get_assessment_meta` repository method (`cube_repository.py:1231`).

---

## §3 API layer plan

### §3.1 Endpoints

Add four routes under `backend/app/api/v1/reports.py`:

```
GET /api/v1/reports/question-summary-paginated/{item_id}
GET /api/v1/reports/question-response-analysis-paginated/{item_id}
GET /api/v1/reports/question-response-analysis-by-teacher/{item_id}
GET /api/v1/reports/question-response-analysis-by-standard-and-teacher/{item_id}
```

All four return the same outer envelope (`assessment`, `kpis`, `data_quality`) plus their variant-specific body.

### §3.2 Pydantic schemas

Add to `backend/app/schemas/reports.py`:

- `QuestionSummaryMatrixPayload { assessment, kpis, questions[], teacher_groups[], grand_total }`
- `QraPaginatedPayload { assessment, kpis, questions[] }` — extends existing QRA fields with `incorrect_students: List[{answer_submission, students: List[str]}]` per question.
- `QraByTeacherPayload { assessment, kpis, teacher_groups[] }`
- `QraByStandardTeacherPayload { assessment, kpis, standard_groups[] }`

### §3.3 Services

Add to `backend/app/services/report_service.py`:

- `build_question_summary_matrix(item_id)` — invokes M1
- `build_qra_paginated(item_id)` — invokes M2 + existing QRA helpers
- `build_qra_by_teacher(item_id)` — invokes M3
- `build_qra_by_standard_teacher(item_id)` — invokes M4

All four reuse the existing `_load_assessment_envelope(item_id)` helper for `assessment` and `kpis`. Reminder: SQLAlchemy `AsyncSession` is single-connection — do NOT `asyncio.gather` parallel cube queries on the same session.

---

## §4 Frontend layer plan

### §4.1 Shared chrome components

The seven PBIX header visuals (logo, H1 banner, KPI strip, H2 Course-and-Unit, H2 Assessment-Type) are byte-identical across all six reports. Build them once:

```
frontend/src/components/app/modules/reports/paginated/
├── PaginatedHeader.tsx              # H1 banner + logo + H2 lines
├── PaginatedKpiStrip.tsx            # 5-cell horizontal strip
├── PaginatedFooter.tsx              # "Generated at … UTC" + page N of M
├── PaginatedCanvas.tsx              # 1280×720 page-sized container, print-CSS-aware
└── shared.ts                        # column color helper (PERF_PINK / YELLOW / GREEN), date format helper
```

Reuse existing `lib/reports/colors.ts` constants. **Key gotcha:** use `PERF_PINK` for `<70%` cells, not `transparent`. The interactive QRA's `cellColor()` is intentionally faded; the paginated rebuilds need the saturated PBIX palette.

### §4.2 Per-report components

```
frontend/src/components/app/modules/reports/qsr/        # QSR family (ord 6/7/16)
├── QuestionSummaryMatrix.tsx        # the per-student matrix table
├── StandardHeaderRow.tsx            # column-group header (highlight=true colors band by performance)
├── TeacherSubtotalRow.tsx           # only rendered when subtotal=teacher
├── GrandTotalRows.tsx               # the 3-row footer (Possible Points / # Correct / Score %)

frontend/src/components/app/modules/reports/qra-paginated/
├── QuestionDetailTablePaginated.tsx # ord 11: flat list + incorrect_students column
├── QuestionByTeacherTable.tsx       # ord 12: teacher group header + questions[]
├── QuestionByStandardTeacherTable.tsx # ord 13: standard header → teacher header → questions + standard_avg footer
```

### §4.3 New pages

```
frontend/src/app/app/reports/question-summary-paginated/[itemId]/page.tsx
frontend/src/app/app/reports/question-response-analysis-paginated/[itemId]/page.tsx
frontend/src/app/app/reports/question-response-analysis-by-teacher/[itemId]/page.tsx
frontend/src/app/app/reports/question-response-analysis-by-standard-and-teacher/[itemId]/page.tsx
```

Use the existing `useSummaryFilters` pattern from `standard-summary/page.tsx`. **Filters are minimal here** — `item_id` is the path param; only optional school/session slicers if any.

### §4.4 Print / PDF rendering

Two options. Pick one during Phase 1 — confirm with team before coding:

| Option | Pros | Cons |
|---|---|---|
| **Print stylesheet only** (`@media print`) | Zero new deps. Browser-native. Users `Cmd+P` → save PDF. | Page break tuning is fiddly; column wrap across pages takes effort. |
| **Server-side Playwright render** | Pixel-perfect, identical across users. Already have Playwright in the test stack. | Extra route on backend; non-trivial perf for 30+ page PDFs. |
| **`@react-pdf/renderer`** | True client PDF; controlled layout primitives. | Re-implements all table layout in PDF primitives; medium complexity. |

Recommendation: **print stylesheet first** (cheap, ships fast), upgrade to Playwright-server-render later if users complain.

---

## §5 Phasing — 4 PRs

To keep blast radius small and ship value early.

### PR 1 — Foundation (shared chrome + tenant config)

- Add `school_logo_url` to `schools` table (if missing) — one migration.
- Expose `school_name` and `school_logo_url` on `get_assessment_meta`.
- Build shared chrome components (`PaginatedHeader`, `PaginatedKpiStrip`, `PaginatedFooter`, `PaginatedCanvas`).
- Add a print stylesheet (`@media print`) covering the shared chrome.
- Verification: render an empty page using the chrome with a real item's meta; print to PDF; confirm header/logo/KPI strip match PBIX layout to ≤5px.

### PR 2 — QSR family (ord 6/7/16)

- Repository M1, schema, service, endpoint.
- React route with `?subtotal=` and `?highlight=` toggles.
- `QuestionSummaryMatrix` component with standard-grouped columns, per-student rows, grand total footer.
- Verification: pick the same assessment as the sample PDF (`Tell Me a Story Weekly Assessment Week 2`); export to PDF; diff against `Paginated - Question Summary Report (1).pdf` page-by-page.

### PR 3 — QRA paginated base (ord 11)

- Repository M2 + new `get_incorrect_choice_students_for_item`.
- Schema, service, endpoint.
- React route + `QuestionDetailTablePaginated`.
- Verification: compare to `Paginated - Question Response Analysis.pdf` — same student-name lists per wrong answer, same sort order (asc by % correct), same pink/yellow/green cells.

### PR 4 — QRA by Teacher and by Standard and Teacher (ord 12/13)

- Repository M3 + M4.
- Two new endpoints + schemas + services.
- Two new React routes + components.
- Verification: compare to the two remaining sample PDFs. Validate `Standard Average:` footer math and `teacher_standard_avg` group header math by hand on at least one standard.

---

## §6 Verification baselines

Anchor numbers we must hit (extract from the sample PDFs before coding to lock them in):

| Report | Sample assessment | Anchor metric | Expected value |
|---|---|---|---|
| QSR base (ord 6) | `Tell Me a Story Wk 2` | Grand total `Possible Points` | 1166 |
| QSR base (ord 6) | same | Grand total `# Correct Answers` | 953 |
| QSR base (ord 6) | same | Grand total `Score %` | 82% |
| QSR base (ord 6) | same | Teacher `Elizabeth Sedlak` group avg | 77.8% |
| QRA paginated (ord 11) | `Module 7 Test` | Sample PDF page count | (record during phase 0) |
| QRA by teacher (ord 12) | `Module 7 Test` | Sample PDF page count | 30 |
| QRA by std/teacher (ord 13) | `Module 7 Test` | Sample PDF page count | 14 |

Add these to `project_kpi_baseline` memory after PR 2 lands so they can't regress silently.

---

## §7 Open questions / risks

1. **`school_logo_url` storage.** Is there already a column or table for school assets? Check Phase 0 before adding a migration. Acceptable forms: `schools.logo_url` text column with a Supabase Storage URL, or an inline base64 string in a `schools.metadata jsonb`.
2. **Multi-select Q12-style scoring in the QSR matrix.** The matrix cell is binary (`0`/`1`), but multi-select questions can score partially. Decision: round any `points_received / points_possible >= 0.5` → 1 else 0? Or only mark `1` when `points_received == points_possible`? PDF shows binary; **need a single sample row from the PDF where a multi-select question has a partial score** to know which rule. Resolve during PR 2.
3. **Pink palette divergence with the interactive QRA.** Once `PaginatedKpiStrip` and `QuestionDetailTablePaginated` use `PERF_PINK` for `<70%`, the interactive QRA still uses `transparent`. Two reports with the "same data" will look different. **Document this in `lib/reports/colors.ts` as intentional**, with a one-line comment citing this synthesis.
4. **Ord 13 standard label form (cpalms long form).** Our `dim_standard.cpalms_standard` carries multiple alias rows per legacy notebook (see `docs/audit/legacy-schoology-cpalms-mapping.md`). The group header must dedupe — pick the lexically-first `cpalms_standard` per `schoology_standard`. Add an explicit unit test for this.
5. **Page break / column wrap behaviour.** PBIX wraps standard columns across page widths (sample QSR PDF page 9 is the tail residual). Our HTML rendering won't naturally do this — for screen mode use a wide horizontal scroller, for print mode rely on `break-inside: avoid` rules. Acceptable to differ from PBIX in screen mode; print mode must match.
6. **`Drill Through Report` / `Report Short Name` slicer** — PBIX-internal helpers used only by the Home page slicer (`legacy-mapping.md` §1.5). Confirmed not needed for the six reports.
7. **`cube_user_summary` page-level filter in ord 12/13** — legacy ballast (`qra-paginated.md` §5 closing note). Do not implement; the runtime behaviour is identical to the `dim_item.Item_Name` filter alone.

---

## §8 Cross-doc anchors

For implementers who land on this file:

- Verbatim DAX for every measure: `docs/audit/reports/question-summary.md` §1, `qra-paginated.md` §0/§1.
- Per-PBIX-page layout maps: same two docs.
- Field → cube column mapping: `docs/audit/reports/legacy-mapping.md` §1.
- Cube grain invariants (Q12 multi-select, latest-attempt window): `legacy-mapping.md` §3.3 — **do not undo**.
- Color tokens: `lib/reports/colors.ts` + `04_dax_measures.dax:250-266` (Performance Color Standard).
- Existing repository methods to reuse: `legacy-mapping.md` §3.5 (assessment meta at `:1231`, school summary at `:235`, questions overall at `:278`, incorrect choices at `:419`).
- Cube SQL: `backend/app/transformations/09_cubes/cube_question_summary.sql`, `cube_question_summary_overall.sql`, `cube_school_summary.sql`.

---

## §9 What NOT to do

- ❌ Do not add new cube columns or migrations to `transformations/`. Every column needed is already produced.
- ❌ Do not collapse multi-select `Q12-style` scoring in the QSR matrix back to a single `GROUP BY` — see `docs/audit/fixes/01_q12_multiselect_applied.md`.
- ❌ Do not reuse `get_questions_overall_for_item` for ord 12/13. It aggregates across sections via `DISTINCT ON`; ord 12/13 need the per-section grain from `cube_question_summary`.
- ❌ Do not import a `cube_user_summary` table to satisfy the legacy PBIX page-filter ballast on ord 12/13.
- ❌ Do not surface the paginated reports as the same React components as the interactive QRA. They look superficially similar but the data shape (per-section, per-standard-teacher) and the conditional formatting (saturated palette) are deliberately different.
- ❌ Do not couple PDF export to backend Playwright on day 1. Ship the print stylesheet first; upgrade only if pixel-perfect export is needed.
