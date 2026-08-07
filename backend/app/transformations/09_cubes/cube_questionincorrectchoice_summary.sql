-- cube_questionincorrectchoice_summary — per-(question, ukey, answer_submission)
-- rollup of student counts and points.
-- Notebook lines 1772-1798 (40_schoology_py_spec.md §7).
--
-- Shape:
--   join fact -> dim_question_data on (question_id, position_number) to bring
--     ukey onto each row (notebook line 1775).
--   ROLLUP over (school_id, question_id, ukey, answer_submission):
--     total_student        = countDistinct(user_uid)
--     total_possible_point = sum(points_possible)
--     total_score          = sum(points_received)
--     grade_average        = sum/sum
--     percentage_incorrect = 1 - grade_average
--   id = sha256(coalesce(school_id) || coalesce(ukey) || coalesce(question_id)
--               || coalesce(answer_submission))
--
-- school_id is in every grouping set so multi-tenant data does not blend.

-- Scoped rebuild: every GROUPING SET is anchored on school_id (there is no ()
-- grand-total set here), so every persisted row belongs to exactly one school
-- and its COUNT(DISTINCT)/SUM aggregates are within-school. Deleting +
-- recomputing only the touched schools' slices is byte-identical to a full
-- rebuild for those schools while leaving untouched schools intact. Empty scope
-- (full rebuild) falls through to the whole-table DELETE — byte-identical to today.
DO $scope$ BEGIN
  IF EXISTS (SELECT 1 FROM _scope_assessments) THEN
    DELETE FROM cube_questionincorrectchoice_summary
    WHERE school_id IN (SELECT DISTINCT school_id FROM _scope_assessments);
  ELSE
    DELETE FROM cube_questionincorrectchoice_summary;
  END IF;
END $scope$;

INSERT INTO cube_questionincorrectchoice_summary (
  id, school_id, question_id, ukey, answer_submission,
  total_student, total_possible_point, total_score,
  grade_average, percentage_incorrect_answers
)
WITH joined AS (
  SELECT
    f.school_id,
    f.user_uid,
    f.question_id,
    f.position_number,
    f.answer_submission,
    f.points_possible,
    f.points_received,
    qd.ukey
  FROM fact_student_submission f
  -- Collapse dim_question_data to ONE ukey per (school, question, position)
  -- before the join. dqd can carry multiple label vintages per question; a raw
  -- join fans every fact row out once per vintage -> doubled distractor/student
  -- counts (2026-07 audit: was live on ~281 assessments). Mirrors the
  -- DISTINCT ON pattern the sibling cubes already use.
  LEFT JOIN (
    SELECT DISTINCT ON (school_id, question_id, position_number)
           school_id, question_id, position_number, ukey
    FROM dim_question_data
    ORDER BY school_id, question_id, position_number, ukey
  ) qd
    ON qd.school_id       = f.school_id
   AND qd.question_id     = f.question_id
   AND COALESCE(qd.position_number, '__NULL__')
       = COALESCE(f.position_number, '__NULL__')
  -- Scoped rebuild: restrict the fact scan to the touched schools so the rollup
  -- recomputes only those slices. Filtering the preserved (left) side keeps the
  -- LEFT JOIN semantics. No-op when _scope_assessments is empty (full rebuild) —
  -- NOT EXISTS InitPlan TRUE, byte-identical to today.
  WHERE (NOT EXISTS (SELECT 1 FROM _scope_assessments)
         OR f.school_id IN (SELECT DISTINCT school_id FROM _scope_assessments))
),
rolled AS (
  SELECT
    school_id,
    question_id,
    ukey,
    answer_submission,
    COUNT(DISTINCT user_uid)        AS total_student,
    SUM(points_possible)            AS total_possible_point,
    SUM(points_received)            AS total_score,
    SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                                    AS grade_average,
    1 - SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                                    AS percentage_incorrect_answers,
    -- sub_level: GROUPING() returns 1 when the column was nulled by the rollup,
    -- 0 when it is a grouping column (real value or real NULL data). Sum is
    -- 0 for the deepest level, 3 for the grand total. Used only to break
    -- hash collisions deterministically.
    GROUPING(question_id) + GROUPING(ukey) + GROUPING(answer_submission)
                                    AS sub_level
  FROM joined
  GROUP BY GROUPING SETS (
    (school_id, question_id, ukey, answer_submission),
    (school_id, question_id, ukey),
    (school_id, question_id),
    (school_id)
  )
),
hashed AS (
  SELECT
    encode(digest(
      COALESCE(school_id::text,   'DEFAULT_SCHOOL_ID')         ||
      COALESCE(ukey,              'DEFAULT_UKEY')              ||
      COALESCE(question_id,       'DEFAULT_QUESTION_ID')       ||
      COALESCE(answer_submission, 'DEFAULT_ANSWER_SUBMISSION'),
      'sha256'
    ), 'hex')                            AS id,
    school_id, question_id, ukey, answer_submission,
    total_student, total_possible_point, total_score,
    grade_average, percentage_incorrect_answers,
    sub_level
  FROM rolled
)
-- DISTINCT ON (id) collapses identical-hash rows from rollup levels that
-- coincide with real-NULL data rows. Prefer the deepest grouping (sub_level=0).
SELECT DISTINCT ON (id)
  id, school_id, question_id, ukey, answer_submission,
  total_student, total_possible_point, total_score,
  grade_average, percentage_incorrect_answers
FROM hashed
WHERE school_id IS NOT NULL
ORDER BY id, sub_level ASC;
