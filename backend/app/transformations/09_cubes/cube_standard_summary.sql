-- cube_standard_summary — per-(item, strand, identifier) totals + averages.
-- Notebook lines 1392-1416 (40_schoology_py_spec.md §7).
--
-- Shape:
--   ROLLUP over (school_id, item_id, strand_id, identifier) on fact directly:
--     total_questions  = countDistinct(question_id)
--     total_standards  = countDistinct(identifier)
--     total_possible_point = sum(points_possible)
--     total_score          = sum(points_received)
--     grade_average        = sum(points_received)/sum(points_possible)
--     percentage_incorrect = 1 - grade_average
--   id = sha256(coalesce(item_id) || coalesce(strand_id) || coalesce(identifier))
--
-- school_id is included in EVERY grouping set so multi-tenant data does not
-- blend across schools. Single-tenant pipelines (e.g. Athenian) collapse to
-- one school_id per row anyway, so row counts and aggregates are unchanged.

-- Scoped rebuild: every GROUPING SET is anchored on school_id (there is no ()
-- grand-total set here), so every persisted row belongs to exactly one school
-- and its COUNT(DISTINCT)/SUM aggregates are within-school. Deleting +
-- recomputing only the touched schools' slices is byte-identical to a full
-- rebuild for those schools while leaving untouched schools intact. Empty scope
-- (full rebuild) falls through to the whole-table DELETE — byte-identical to today.
DO $scope$ BEGIN
  IF EXISTS (SELECT 1 FROM _scope_assessments) THEN
    DELETE FROM cube_standard_summary
    WHERE school_id IN (SELECT DISTINCT school_id FROM _scope_assessments);
  ELSE
    DELETE FROM cube_standard_summary;
  END IF;
END $scope$;

INSERT INTO cube_standard_summary (
  id, school_id, item_id, strand_id, identifier,
  total_questions, total_standards,
  total_possible_point, total_score,
  grade_average, percentage_incorrect_answers
)
WITH rolled AS (
  SELECT
    school_id,
    item_id,
    strand_id,
    identifier,
    COUNT(DISTINCT question_id)    AS total_questions,
    COUNT(DISTINCT identifier)     AS total_standards,
    SUM(points_possible)           AS total_possible_point,
    SUM(points_received)           AS total_score,
    SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                                   AS grade_average,
    1 - SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                                   AS percentage_incorrect_answers,
    -- sub_level: GROUPING() returns 1 when the column was nulled by the rollup,
    -- 0 when it is a grouping column (real value or real NULL data). Used
    -- only to break hash collisions deterministically.
    GROUPING(item_id) + GROUPING(strand_id) + GROUPING(identifier)
                                   AS sub_level
  FROM fact_student_submission
  -- Scoped rebuild: restrict the fact scan to the touched schools so the rollup
  -- recomputes only those slices. No-op when _scope_assessments is empty
  -- (full rebuild) — NOT EXISTS InitPlan TRUE, byte-identical to today.
  WHERE (NOT EXISTS (SELECT 1 FROM _scope_assessments)
         OR school_id IN (SELECT DISTINCT school_id FROM _scope_assessments))
  GROUP BY GROUPING SETS (
    (school_id, item_id, strand_id, identifier),
    (school_id, item_id, strand_id),
    (school_id, item_id),
    (school_id)
  )
),
hashed AS (
  SELECT
    encode(digest(
      COALESCE(school_id::text, 'DEFAULT_SCHOOL_ID') ||
      COALESCE(item_id,         'DEFAULT_ITEM_ID')   ||
      COALESCE(strand_id,       'DEFAULT_STRAND_ID') ||
      COALESCE(identifier,      'DEFAULT_IDENTIFIER'),
      'sha256'
    ), 'hex')                          AS id,
    school_id, item_id, strand_id, identifier,
    total_questions, total_standards,
    total_possible_point, total_score,
    grade_average, percentage_incorrect_answers,
    sub_level
  FROM rolled
)
-- DISTINCT ON (id): when a real-NULL data row collides with a rollup-NULL
-- subtotal row on the same hash, prefer the deepest (lowest sub_level) row
-- — that is the one with the most concrete grouping context. Re-runs are
-- deterministic because sub_level is a derived value (no ORDER BY ties).
SELECT DISTINCT ON (id)
  id, school_id, item_id, strand_id, identifier,
  total_questions, total_standards,
  total_possible_point, total_score,
  grade_average, percentage_incorrect_answers
FROM hashed
WHERE school_id IS NOT NULL
ORDER BY id, sub_level ASC;
