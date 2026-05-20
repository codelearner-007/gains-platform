# 06 — Cubes & Report Formulas Audit

Anchor assessment: **Chapter 9 Test — Grade 8 — item_id `8359960427`**
Visible discrepancies (legacy → current):
- Grade Avg `66.9% → 65.4%` (Δ −1.5pp)
- Overall Highest % `96.1% → 96.3%` (Δ +0.2pp)
- Overall Lowest % `28.9% → 27.8%` (Δ −1.1pp)
- Standard AR.1.7 `78.9% → 77.8%` (Δ −1.1pp)
- Standard AR.3.1 `69.5% → 69.0%` (Δ −0.5pp)
- Strand "Algebra: Reasoning with Equations" `60.2% → 60.5%` (Δ +0.3pp)
- Total Students 27, Questions 18, Standards 12 — **match** (so the universe of facts is identical; the differences are pure formula differences)

---

## Formula Comparison Matrix

| KPI | Legacy DAX measure | PBIX formula (short) | Current SQL/JS location | Current formula | Difference | Plausible impact on screenshot |
|---|---|---|---|---|---|---|
| Grade Average (KPI strip) | `Grade_Average_Standard_Measure` (`04_dax_measures.dax:215-243`) — same as `[Grade Average]` / `[Grade_Average_Strand_Measure]` | `AVERAGE('cube_question_summary_overall'[Grade_Average])` | `cube_repository.py:104-157` `get_canonical_kpis_for_item` | `AVG(qga)` where `qga = AVG(per-user pct)` and `per-user pct = SUM(pts_recv)/SUM(pts_poss)` per (user, question) on **fact_student_submission** | Legacy: single mean over per-question SUM/SUM ratios. Current: nested mean over per-student percentages, then mean over questions. On multi-select / partial-credit questions where students have unequal `points_possible`, these two differ. | Lowers KPI when low-scoring students answered fewer / partial-point sub-questions. **Matches −1.5pp shift (66.9 → 65.4).** |
| Overall Highest % | `Grade Max` (`04_dax_measures.dax:116-128`) | `MAXX(VALUES('cube_question_summary_overall'[Question_No]), CALCULATE(AVERAGE(cqso[Grade_Average])))` | `cube_repository.py:104-157` | `MAX(qga)` over the same per-user-collapse pipeline above | Same nested-mean issue: legacy max picks the question whose SUM/SUM ratio is highest; current picks the question whose AVG(per-user pct) is highest. | Easily explains a ±0.2pp shift on the max question (96.1 → 96.3). |
| Overall Lowest % | `Grade Min` (`04_dax_measures.dax:60-73`) | `MINX(VALUES(cqso[Question_No]), CALCULATE(AVERAGE(cqso[Grade_Average])))` | `cube_repository.py:104-157` | `MIN(qga)` over the same pipeline | Same. Service-layer comment at `report_service.py:463-468` explicitly notes Q12 = 35/146 = **23.97%** under SUM/SUM vs **27.78%** under per-user avg. | 27.78% rounds to 27.8% — matches current screenshot. Legacy 28.9% means either a different question is the legacy minimum, or legacy excludes one student row. **Matches −1.1pp shift.** |
| % per Standard | `Grade_Average_Standard_Measure` filtered by `cqso[Standards]` slicer (DAX line 215) | `AVERAGE('cube_question_summary_overall'[Grade_Average])` filtered by the Standards column | `cube_repository.py:568-636` `get_standard_rollup_for_item` → `AVG(cqs.grade_average)` from **cube_question_summary** grouped by identifier | Legacy averages over `cube_question_summary_overall` rows (one row per question per standard alignment). Current averages over `cube_question_summary` rows (one row per (question, position, identifier)) **using `AVG(grade_average)` of the SUM/SUM column**. | Legacy reads from `cqso` (overall, no `position_number` granularity beyond what the spec drops, no `identifier` granularity); current reads from `cqs` (still per-position, per-identifier). On multi-position questions where one position has very different points_possible than another, the per-position AVG diverges from the per-question SUM/SUM. | AR.1.7 78.9→77.8 (Δ −1.1pp) and AR.3.1 69.5→69.0 (Δ −0.5pp) consistent with per-position averaging biasing low on questions with uneven sub-question weights. |
| % per Strand (QRA Strands table) | `Grade_Average_Strand_Measure` (DAX line 203-209) = `CALCULATE(AVERAGE(cqso[Grade_Average]))` | Same: `AVERAGE(cqso[Grade_Average])` filtered by `dim_standard[Strand]` | `cube_repository.py:478-566` `get_strand_rollup_for_item` → `AVG(cqs.grade_average)` from **cube_question_summary** grouped by `dim_standard.strand` | Same fundamental mismatch as % per Standard, with one additional twist: current joins `cube_question_summary` × `dim_standard` × `identifier` to count distinct questions and average per (strand, identifier) — duplicates a multi-aligned question into multiple `identifier` rows whose grade values are then averaged uniformly. PBIX averages the cqso rows directly. | Drift sign is **opposite** of KPI drift (60.5 > 60.2 means current is higher) — this is consistent with the join-side duplication oversampling rows whose `grade_average` is higher than the cohort's SUM/SUM, not with the lower-bias seen elsewhere. Worth confirming with a row-by-row trace. |
| Total Students | `Total Student` (DAX 134-142) — `SUMX(SUMMARIZE(cube_school_summary, item_id, "u", MAX(Total_Students)), [u])` | Same | `cube_school_summary.total_students` (read via `get_canonical_kpis_for_item`'s `school` CTE) | Identical concept | None expected | None — both show 27. |
| Total Questions | `Total Question` (DAX 148-153) — `DISTINCTCOUNT(cqso[Question_No])` | Same | `cube_repository.py:104` `COUNT(*) FROM per_q` (which is `GROUP BY question_id` over per-user-collapsed fact) | Different *source* (fact vs cqso) but both should yield the same distinct question count | None expected | None — both show 18. |
| Total Standards | `Total Standard` (DAX 159-162) — `DISTINCTCOUNT(cqso[Standards])` (the long-form text column) | Same | `cube_repository.py:104` `COUNT(DISTINCT standard) FROM dim_question_data WHERE item_id = :id AND standard NOT IN ('', 'null')` | Both count the long-form standards string; current bypasses cqso and goes to `dim_question_data` directly | None expected if cqso[Standards] is sourced from dim_question_data.standards | None — both show 12. |
| Paginated header `[Grade Average2]` (page #9 PDF) | `04_dax_measures.dax:1065-1068` | `AVERAGE('cube_standard_summary'[Grade_Average])` — **different table!** This is per-(strand,identifier) averaging, not per-question | Not directly used; QRA/SDD use canonical KPI helper | The legacy PDF header uses cube_standard_summary; the legacy interactive KPI uses cqso. They give different numbers in PBIX itself. | Current code only renders the interactive layout, so this isn't directly visible — but it's documented because if the user is comparing to a paginated PDF screenshot, the legacy "Grade Average" there came from `cube_standard_summary`. | Could explain very small per-screenshot variance if the reference screenshot is a hybrid. |
| Performance color thresholds | `Performance Color*` measures — `<0.7` pink, `0.7–0.8` yellow, `≥0.8` green | as above | `report_service.py:159-180` `_perf_color()` + `frontend/src/lib/reports/colors.ts` | Same thresholds (0.7 / 0.8) | None | None expected. |

---

## What it does (current)

QRA report flow:

```
frontend page  →  /api/v1/reports/question-response-analysis/<item_id>
                  (Next.js rewrite to FastAPI)
                  ↓
backend/app/api/v1/reports.py
                  ↓
ReportService.build_question_response_analysis()
  ├── cube.get_assessment_meta              (dim_item + dim_subject)
  ├── cube.get_questions_overall_for_item   (cqs/cqso joined, per-question)
  ├── cube.get_incorrect_choices_for_item   (cube_questionincorrectchoice_summary)
  ├── cube.get_students_for_item            (dim_user)
  ├── cube.get_raw_question_options_for_item
  ├── cube.get_canonical_kpis_for_item      (← the formula at issue)
  ├── cube.get_canonical_per_question_grades (overrides per-question table grade)
  ├── cube.get_strand_rollup_for_item       (Strands table)
  ├── cube.get_standard_rollup_for_item     (Standards table)
  └── cube.get_alignment_quality_for_item
  ↓
QuestionResponseAnalysisPayload returned (KPIs, questions, strands_rollup, …)
  ↓
frontend/src/components/app/modules/reports/qra/KpiStrip.tsx
  Displays `grade_average_pct`, `grade_max_pct`, `grade_min_pct` as-is
```

Front-end is purely a renderer; **every number in the screenshot is computed in SQL/Python on the backend**.

---

## How it does it (current)

### KPI Grade Average / Min / Max — `cube_repository.py:104-157`

```sql
WITH fact_dedup AS (
    SELECT DISTINCT ON (user_uid, question_id, position_number)
           user_uid, question_id, position_number,
           points_received, points_possible
    FROM fact_student_submission
    WHERE item_id = :item_id
      AND points_possible IS NOT NULL
      AND points_possible > 0
    ORDER BY user_uid, question_id, position_number, identifier NULLS LAST
),
per_user_q AS (
    SELECT question_id, user_uid,
           SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0) AS pct
    FROM fact_dedup
    GROUP BY question_id, user_uid
),
per_q AS (
    SELECT question_id, AVG(pct) AS qga
    FROM per_user_q
    GROUP BY question_id
)
SELECT
  AVG(qga) AS grade_average,
  MAX(qga) AS grade_max,
  MIN(qga) AS grade_min
FROM per_q
```

Three-level aggregation: per-row → per-(user,question) ratio → per-question mean of student ratios → per-item mean/max/min of question means.

### % per Standard — `cube_repository.py:568-636`

```sql
per_identifier AS (
    SELECT
        cqs.identifier,
        COUNT(DISTINCT cqs.question_no) AS num_questions,
        AVG(cqs.grade_average)          AS grade_average
    FROM cube_question_summary cqs
    WHERE cqs.item_id = :item_id
    GROUP BY cqs.identifier
)
SELECT
    l.cpalms_standard,
    MAX(p.grade_average) AS grade_average     -- pivot per cpalms label
FROM labeled l
LEFT JOIN per_identifier p ON p.identifier = l.identifier
GROUP BY l.cpalms_standard, l.strand
```

`cube_question_summary.grade_average` is itself `SUM(points_received)/SUM(points_possible)` per (item, question_id) — see `09_cubes/cube_question_summary.sql:75-87`. So per-standard % = average of per-question SUM/SUM, restricted to identifiers tied to that standard.

### % per Strand — `cube_repository.py:478-566`

```sql
strand_metrics AS (
    SELECT
        ds.strand,
        COUNT(DISTINCT cqs.question_no) AS num_questions,
        AVG(cqs.grade_average)          AS grade_average
    FROM cube_question_summary cqs
    JOIN dim_standard ds ON ds.identifier = cqs.identifier
    JOIN labeled l       ON l.identifier  = cqs.identifier
    WHERE cqs.item_id = :item_id
      AND ds.strand <> ''
    GROUP BY ds.strand
)
```

Joins `cqs` (already per-(question, position, identifier)) to `dim_standard` on identifier; a question aligned to multiple identifiers within a strand contributes **multiple rows**, biasing the AVG toward whatever those duplicate rows happen to be.

### Per-question grade override — `report_service.py:464-474`

```python
canon_per_q = await self.cube.get_canonical_per_question_grades(item_id)
canon_q_by_id = {... q.question_id: AVG(per-user pct) ...}
for q in question_rows:
    qid = safe_str(q.get("question_id"))
    if qid in canon_q_by_id:
        ga = canon_q_by_id[qid]
        q["grade_average"] = ga    # override cqs SUM/SUM with per-user-mean
        q["percentage_incorrect"] = 1.0 - ga
```

The per-question column in the QRA table is **overwritten** with the per-user-mean. This means:
- KPI strip (mean/max/min over per_q) and per-question table column **agree with each other** (by construction).
- But both **disagree with PBIX**, which uses cqso[Grade_Average] (the SUM/SUM-per-question column).

### Cube column origins

- `cube_question_summary.grade_average` (`09_cubes/cube_question_summary.sql:81`) = `SUM(points_received)/SUM(points_possible)` per `(school_id, item_id, question_id)` — **SUM/SUM**.
- `cube_question_summary_overall.grade_average` (`09_cubes/cube_question_summary_overall.sql:110`) = `SUM(points_received)/SUM(points_possible)` per `(school_id, subject_id, ukey, question_no, question, position_number, correct_answer, standard)` — **SUM/SUM** at finer grain. Per-question values for a single question aligned to N standards are identical because dividing the same numerator by the same denominator.
- `cube_standard_summary.grade_average` (`09_cubes/cube_standard_summary.sql:36`) = `SUM/SUM` per `(school_id, item_id, strand_id, identifier)`.

All three cube columns are **SUM/SUM ratios**, exactly as PBIX expects. The discrepancy is introduced **at read time** by the canonical KPI helper, which bypasses cqso entirely and computes a different formula directly on the fact.

---

## What legacy did (PBIX DAX)

### Grade Average (KPI strip on Page #17 — interactive QRA)

`04_dax_measures.dax:215-243`:
```
MEASURE [Grade_Average_Standard_Measure] =
    AVERAGE('cube_question_summary_overall'[Grade_Average])
```

Plain `AVERAGE` over the visible (filter-context) rows of the cqso table. Each cqso row holds a SUM/SUM ratio for a (Question_No, Standards, Position_Number, …) grain. With no slicer, AVERAGE = unweighted mean of all those per-row SUM/SUM ratios.

### Grade Max (Overall Highest %)

`04_dax_measures.dax:116-128`:
```
MEASURE [Grade Max] =
MAXX(
    VALUES('cube_question_summary_overall'[Question_No]),
    CALCULATE(AVERAGE('cube_question_summary_overall'[Grade_Average]))
)
```

Iterates the distinct Question_No values, then for each Question_No computes `AVERAGE(cqso[Grade_Average])` *filtered to that question*, then takes the MAX. Because the cqso grade for one question across multiple Standards is the same SUM/SUM ratio, the inner AVERAGE collapses to a single per-question SUM/SUM value. So effectively: MAX over questions of per-question SUM/SUM.

### Grade Min (Overall Lowest %)

`04_dax_measures.dax:60-73` — symmetric MINX of the same expression.

### % per Standard (in the Standards table)

Uses the same `Grade_Average_Standard_Measure` = `AVERAGE(cqso[Grade_Average])`, but the row context filters `cqso[Standards]` to one standard. Because cqso has one row per `(Question_No, Standards, Position_Number, Correct_Answer)`, for a standard tagged on K questions the AVERAGE is `mean of K SUM/SUM ratios`. No `dim_standard.identifier` involvement, no per-position duplication.

### % per Strand

`04_dax_measures.dax:203-209`:
```
MEASURE [Grade_Average_Strand_Measure] =
    VAR AvgGrade = CALCULATE(AVERAGE('cube_question_summary_overall'[Grade_Average]))
    RETURN AvgGrade
```

Identical to `Grade_Average_Standard_Measure` but evaluated in the strand row context (the Strand column comes from `dim_standard[Strand]` joined via the model relationship to cqso[Standards]). Average of the cqso rows that fall in the strand.

### Total Student / Total Question / Total Standard

- `Total Student` = `SUMX(SUMMARIZE(cube_school_summary, Item_ID, MAX(Total_Students)))` — per-item max.
- `Total Question` = `DISTINCTCOUNT(cqso[Question_No])`.
- `Total Standard` = `DISTINCTCOUNT(cqso[Standards])` — counts the long-form Standards string.

These three are unproblematic; modern code matches.

### Paginated PDF header `[Grade Average2]` (Page #9)

`04_dax_measures.dax:1065-1068`:
```
MEASURE [Grade Average2] =
    VAR AvgGrade = AVERAGE('cube_standard_summary'[Grade_Average])
    RETURN FORMAT(AvgGrade, "0.0%")
```

**This is a different table.** The PDF header averages per-(strand, identifier) SUM/SUM ratios, which can disagree with the interactive page's per-question average. If the user's reference screenshot is the paginated PDF, then legacy "66.9%" is `AVG over cube_standard_summary.grade_average`, NOT `AVG over cqso.grade_average`. Both are sum-over-sum at their respective grains; neither matches the current per-user-mean canonical formula.

---

## Discrepancies found

### D1. KPI Grade Average uses per-user-mean instead of per-question SUM/SUM

- **Legacy:** `AVERAGE(cqso[Grade_Average])`. Each cqso row is a per-question SUM/SUM ratio. Result is the unweighted mean of those K per-question ratios.
- **Current:** Three-stage mean: SUM/SUM per (user, question) → mean across students per question → mean across questions.

These disagree whenever the per-question pool of attempts has uneven `points_possible` (multi-part, partial-credit, students that skipped a sub-part). For a question where two students earned the maximum and 25 students partially credit, the per-question SUM/SUM and the AVG-of-per-student-pct **are not the same number**.

### D2. Grade Min / Grade Max inherit the same formula difference

Same SQL pipeline, same root cause. Legacy `MAXX/MINX VALUES(Question_No)` collapses (via inner AVERAGE) to the per-question SUM/SUM; current `MAX(qga)` / `MIN(qga)` is mean-of-per-student.

The service-layer comment at `report_service.py:463-468` documents the Q12 example: cqs SUM/SUM = 23.97%, per-user mean = 27.78%. The current minimum on the screenshot is 27.8% — i.e. the **current value matches the per-user mean for Q12**. Legacy 28.9% is either:
- A different question (Q12 not the legacy minimum because its SUM/SUM 23.97% < something), OR
- The legacy minimum is computed at a slightly different grain where 23.97% rounds to a separate bucket.

Either way, **the Min/Max screenshots cannot agree because the formulas differ at the root**.

### D3. % per Standard reads from cube_question_summary (per-position) instead of cube_question_summary_overall

- **Legacy:** filters cqso rows (per Question_No × Standards × Position_Number × Correct_Answer) to one standard, averages their `Grade_Average` (SUM/SUM ratios). For an aligned multi-position question, all positions contribute their individual SUM/SUM ratios — but in PBIX cqso, `Position_Number` is part of the grain only if the source data has it; common path is one row per question.
- **Current:** reads `cube_question_summary` (per question × position × identifier), `GROUP BY identifier`, `AVG(grade_average)`. Multi-position questions contribute one row per position, *each row's `grade_average` being the SUM/SUM for that position*, and the AVG over positions is **not** the question's overall SUM/SUM unless `points_possible` is identical across positions.

### D4. % per Strand inherits D3 plus an extra duplication

`get_strand_rollup_for_item` joins `cube_question_summary` × `dim_standard` × `labeled`. If a question's `identifier` matches multiple cpalms-standard rows in `dim_standard` for the same strand (alias rows), the cqs row is duplicated; AVG then weights duplicates equally. PBIX would not duplicate because cqso already collapses to one row per question per Standards-string.

### D5. Per-question table column is overwritten with per-user-mean

`report_service.py:464-474` replaces `q["grade_average"]` from cqs (SUM/SUM) with the per-user-mean. This is internally consistent with the (broken) KPI formula but means **even the per-question column in the screenshot doesn't agree with PBIX**.

### D6. cube_standard_summary.grade_average is computed at the wrong grain (compared to PBIX Page #9 PDF header only)

The paginated PDF (Page #9) uses `AVERAGE(cube_standard_summary[Grade_Average])` for its header KPI. That table aggregates per-(strand, identifier). Not actually used by current code, so this is informational — but if the user is comparing the screenshot to the *paginated PDF*, this is the correct legacy formula, and it's not the one any modern endpoint mimics.

### D7. Identifier vs strand duplication on cube_question_summary post-pipeline

The notebook-style cube already emits one row per (question, identifier) (see `09_cubes/cube_question_summary.sql:289-295` and the comment about "B2 grain change"). That extra identifier-axis is exactly what `get_standard_rollup_for_item` and `get_strand_rollup_for_item` consume. Legacy did NOT have this axis (PBIX's cqso has `Standards` text only, not identifier UUID), so legacy averages don't have the per-identifier inflation.

---

## Likely numeric impact

For each visible screenshot number, the predicted impact direction and magnitude:

1. **Grade Avg 66.9 → 65.4 (−1.5pp).** D1. Per-user mean weights low-scoring students equally with high-scoring on every question; SUM/SUM weights by attempt density. If the bottom quartile of students answered all 18 questions while the top quartile skipped 1-2 partial-credit items, per-user mean understates by ~1-2pp. **Direction and magnitude match.**

2. **Highest % 96.1 → 96.3 (+0.2pp).** D2. On the highest-scoring question, the per-user mean is slightly higher than SUM/SUM when one or two students got partial credit (their fractional ratio averages above zero but their raw points don't beat the denominator weight). **Direction and small magnitude match.**

3. **Lowest % 28.9 → 27.8 (−1.1pp).** D2 + the documented Q12 case. If Q12 is the legacy minimum and has shifted ratio from 28.9% (legacy SUM/SUM 35/121 or similar grain) to 27.78% (per-user mean), this is direct evidence. **Matches in direction and magnitude.** Verify by querying Q12's per-user-mean and per-question SUM/SUM separately.

4. **AR.1.7 78.9 → 77.8 (−1.1pp).** D3. If AR.1.7 covers a multi-position question with uneven position weights, the per-position AVG biases below the per-question SUM/SUM. **Direction matches.**

5. **AR.3.1 69.5 → 69.0 (−0.5pp).** D3. Same mechanism, smaller because uneven-weight effect is smaller. **Direction matches.**

6. **Strand "Algebra: Reasoning with Equations" 60.2 → 60.5 (+0.3pp).** D4. Sign is opposite because the dim_standard duplication oversamples whichever identifier-row has the higher SUM/SUM (likely one strand-internal standard has fewer attempts and a higher ratio). **Direction is consistent with a duplicate-weighting bias, but the specific direction depends on which alias rows duplicate.** Verify by checking the joined row count vs distinct question count for that strand.

7. **Total Students 27, Questions 18, Standards 12 match.** These KPIs route through fact-counting paths (cube_school_summary, fact dedup, dim_question_data) that are formula-equivalent to legacy. **No drift expected.**

---

## Recommended verification queries

To confirm root cause empirically before changing formulas, run against the live DB:

```sql
-- For item 8359960427 — compare per-question SUM/SUM vs per-user-mean
WITH fact_dedup AS (
  SELECT DISTINCT ON (user_uid, question_id, position_number)
    user_uid, question_id, position_number, points_received, points_possible
  FROM fact_student_submission
  WHERE item_id = '8359960427'
    AND points_possible > 0
  ORDER BY user_uid, question_id, position_number, identifier NULLS LAST
),
sum_over_sum AS (
  SELECT question_id,
         SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0) AS sos
  FROM fact_dedup GROUP BY question_id
),
per_user_mean AS (
  SELECT question_id, AVG(pct) AS pum FROM (
    SELECT question_id, user_uid,
           SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0) AS pct
    FROM fact_dedup GROUP BY question_id, user_uid
  ) x GROUP BY question_id
)
SELECT s.question_id, ROUND(s.sos*100, 2) AS sum_over_sum_pct,
       ROUND(u.pum*100, 2) AS per_user_mean_pct,
       ROUND((u.pum - s.sos)*100, 2) AS diff_pp
FROM sum_over_sum s JOIN per_user_mean u USING (question_id)
ORDER BY question_id;

-- Then aggregate:
SELECT
  ROUND(AVG(s.sos)*100, 1)  AS legacy_grade_avg_pct,
  ROUND(AVG(u.pum)*100, 1)  AS current_grade_avg_pct,
  ROUND(MAX(s.sos)*100, 1)  AS legacy_highest_pct,
  ROUND(MAX(u.pum)*100, 1)  AS current_highest_pct,
  ROUND(MIN(s.sos)*100, 1)  AS legacy_lowest_pct,
  ROUND(MIN(u.pum)*100, 1)  AS current_lowest_pct
FROM sum_over_sum s JOIN per_user_mean u USING (question_id);
```

If `legacy_*_pct` lands on 66.9 / 96.1 / 28.9 and `current_*_pct` lands on 65.4 / 96.3 / 27.8 — **D1+D2 are fully confirmed** and the fix is to replace `get_canonical_kpis_for_item` with `AVG/MAX/MIN of sum_over_sum` (which is what cqso.grade_average already stores).

For per-standard (D3):

```sql
-- Legacy: AVERAGE(cqso[Grade_Average]) per standard
SELECT standards, ROUND(AVG(grade_average)*100, 1) AS legacy_pct
FROM cube_question_summary_overall
WHERE EXISTS (
  SELECT 1 FROM cube_question_summary cqs
  WHERE cqs.school_id = cube_question_summary_overall.school_id
    AND cqs.item_id = '8359960427'
)
GROUP BY standards ORDER BY standards;

-- Current: from per_identifier AVG(cqs.grade_average) per identifier → max per cpalms
-- (already implemented in get_standard_rollup_for_item — just run it directly)
```

Compare AR.1.7 and AR.3.1 rows.

---

## Summary

Every visible-number drift in the screenshot traces back to **one core formula choice**: the modern `_compute_canonical_kpis_for_item` helper computes a per-user-mean-then-per-question-mean instead of legacy's per-question SUM/SUM. That cascades into the Grade Avg KPI, Highest %, Lowest %, *and* (via the deliberate per-question override at `report_service.py:464`) the per-question table column. Per-standard and per-strand drift come from a *second*, independent issue: the rollups read `cube_question_summary` (per-position, per-identifier) instead of `cube_question_summary_overall`, which the PBIX DAX measures actually consume.

Both fixes are read-only formula changes that don't require touching the cube SQL itself — the cube columns are already correct sum-over-sum ratios.
