# Fix 1 Applied — Q12 Multi-Select Per-Question Average

## Status: APPLIED on 2026-05-20.

## What changed
Two cube SQLs:

- `backend/app/transformations/09_cubes/cube_question_summary.sql` — `totals` CTE now pre-aggregates to one row per `(school, item, question, user, submission, position_number)` using `MAX(points_received), MAX(points_possible)` before the SUM/SUM.
- `backend/app/transformations/09_cubes/cube_question_summary_overall.sql` — same pre-aggregation applied in the cqso `totals` CTE, starting from `latest_with_hash`.

Other cubes were not touched. The fact table and parser were not touched.

## Why
Schoology shreds multi-select ("Select All That Apply") questions into one row per selected option, repeating the same per-question fractional score on every shredded row. SUM-over-rows therefore inflates both numerator and denominator by `(# options selected by that student)`, which varies across students. The downward bias on the per-question average ranged 2–8 pp on multi-select questions; Q12 of Chapter 9 Test showed 23.97% in our cube vs Schoology's authoritative 27.78%.

Verified against three independent legacy sources in `docs/audit/bug-research/01_q12_multiselect.md`:

1. Schoology Submission-Summary CSV column 19 (`Question 12`) — sum across 27 students = 7.5 → mean = 0.2778.
2. Schoology Question-Data CSV — `Average Points Earned = 0.28`.
3. Legacy PySpark notebook AND `40_schoology_py_spec.md:606,673` — same bug, displays 23.97% in legacy PBIX too. Fix aligns with Schoology, intentionally diverges from legacy.

## Numeric outcome (Chapter 9 Test, item `8359960427`)

| Metric | Before | After | Schoology truth |
|---|---|---|---|
| Q12 `cube_question_summary.grade_average` | 23.97% | 27.78% | 27.78% ✓ |
| Q12 `total_possible_point` | 146 | 27 | 27 (one per student) ✓ |
| Q12 `total_score` | 35 | 7.5 | 7.5 ✓ |
| All other 17 questions | unchanged | unchanged | matches Schoology to ≤0.5 pp ✓ |
| QRA screenshot KPIs (Grade Avg / Highest / Lowest) | 65.4 / 96.3 / 27.8 | 65.4 / 96.3 / 27.8 | (unchanged — read helper already corrected) |

The screenshot's KPI strip does not move because the read helper already computed per-question per-student-mean averaging (not SUM/SUM). The fix corrects the cube's own `grade_average` column, which is what populates the "Question Summary Report" table at the bottom of the QRA — Q12's row there will now show 27.78%.

## Why MAX-collapse is safe
Probe confirmed zero clusters where rows within `(school, item, question, user, submission, position_number)` had non-identical `points_received`:

```sql
SELECT COUNT(*) FROM (
  SELECT school_id, item_id, question_id, user_uid, submission, position_number
  FROM fact_student_submission
  GROUP BY school_id, item_id, question_id, user_uid, submission, position_number
  HAVING COUNT(*) > 1 AND COUNT(DISTINCT points_received) > 1
) unsafe;
→ 0
```

Every existing cluster (multi-select option shred OR standards alias fanout) has identical `pr`/`pp` across rows, so MAX is a no-op on the value and a deduplicating reduction on row count. Single-row clusters pass through unchanged.

## Question types and their behavior under the fix

| Type | Cluster shape | MAX-collapse effect |
|---|---|---|
| Single multiple-choice | 1 row per (user, question, position); standards alias fanout = N rows with identical pr/pp | Collapses alias-fanout cleanly; ratio unchanged |
| Multi-select | Variable # rows per (user, question) — one per selected option, each carrying same pr/pp | Collapses to 1 row per student; ratio FIXED |
| Fill-in-the-blank with sub-questions | Different `position_number` per sub-question | NOT collapsed across sub-questions (grouping key includes position_number); per-sub-question alias-fanout still collapses |
| Ordering / matching | Different `position_number` per pair | NOT collapsed across pairs |

## What the fix did NOT do
- Touch `fact_student_submission` grain (still one row per shredded option).
- Touch `cube_questionincorrectchoice_summary` (still reads fact directly to keep per-option breakdown).
- Change ingestion / parser logic.
- Affect the screenshot KPI strip (already correct via the read helper).

## Verification commands

```sql
-- 1) Q12 cube grade_average now 27.78%
SELECT question_id, ROUND(grade_average*100,2) AS pct
FROM cube_question_summary
WHERE item_id='8359960427' AND question_id='2269602178'
LIMIT 1;
-- Expected: 27.78

-- 2) Q12 total_possible_point now 27 (was 146)
SELECT question_id, total_possible_point, total_score
FROM cube_question_summary
WHERE item_id='8359960427' AND question_id='2269602178'
LIMIT 1;
-- Expected: 27, 7.5

-- 3) Other questions unchanged
SELECT question_id, ROUND(grade_average*100,2) AS pct
FROM cube_question_summary
WHERE item_id='8359960427' AND question_id='2269602176'
LIMIT 1;
-- Expected: 96.30 (unchanged)

-- 4) Safety invariant — zero unsafe clusters across entire DB
SELECT COUNT(*) FROM (
  SELECT school_id, item_id, question_id, user_uid, submission, position_number
  FROM fact_student_submission
  GROUP BY school_id, item_id, question_id, user_uid, submission, position_number
  HAVING COUNT(*) > 1 AND COUNT(DISTINCT points_received) > 1
) unsafe;
-- Expected: 0
```

## Pre-existing test failure (not caused by this fix)
`tests/api/test_reports_sdd.py::test_sdd_unaligned_assessment_signals_missing_alignment` fails the same way on the main branch before the fix. Confirmed by `git stash` + cube rebuild + test re-run — failure identical. Unrelated; should be tracked separately.
