-- cube_school_summary — per-(school, subject, item) totals + averages.
-- Notebook lines 1367-1391 (40_schoology_py_spec.md §7).
--
-- Shape:
--   ROLLUP over (school_id, subject_id, item_id) on fact directly:
--     total_questions  = countDistinct(question_id)
--     total_standards  = countDistinct(identifier)
--     total_students   = countDistinct(user_uid)
--     total_possible_point = sum(points_possible)
--     total_score          = sum(points_received)
--     grade_average        = sum(points_received) / sum(points_possible)
--     percentage_incorrect = 1 - grade_average
--   id = sha256(coalesce(school_id) || coalesce(subject_id) || coalesce(item_id))
--
-- TRUNCATE+INSERT idempotency: deterministic.

TRUNCATE TABLE cube_school_summary;

INSERT INTO cube_school_summary (
  id, school_id, school_id_csv, subject_id, item_id,
  total_questions, total_standards, total_students,
  total_possible_point, total_score,
  grade_average, percentage_incorrect_answers
)
WITH rolled AS (
  SELECT
    school_id,
    MAX(school_id_csv)             AS school_id_csv,
    subject_id,
    item_id,
    COUNT(DISTINCT question_id)    AS total_questions,
    COUNT(DISTINCT identifier)     AS total_standards,
    COUNT(DISTINCT user_uid)       AS total_students,
    SUM(points_possible)           AS total_possible_point,
    SUM(points_received)           AS total_score,
    SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                                   AS grade_average,
    1 - SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                                   AS percentage_incorrect_answers,
    GROUPING(school_id) + GROUPING(subject_id) + GROUPING(item_id)
                                   AS sub_level
  FROM fact_student_submission
  GROUP BY GROUPING SETS (
    (school_id, subject_id, item_id),
    (school_id, subject_id),
    (school_id),
    ()
  )
),
hashed AS (
  SELECT
    encode(digest(
      COALESCE(school_id::text, 'DEFAULT_SCHOOL_ID') ||
      COALESCE(subject_id,      'DEFAULT_SUBJECT_ID') ||
      COALESCE(item_id,         'DEFAULT_ITEM_ID'),
      'sha256'
    ), 'hex')                           AS id,
    school_id, school_id_csv, subject_id, item_id,
    total_questions, total_standards, total_students,
    total_possible_point, total_score,
    grade_average, percentage_incorrect_answers,
    sub_level
  FROM rolled
)
SELECT DISTINCT ON (id)
  id, school_id, school_id_csv, subject_id, item_id,
  total_questions, total_standards, total_students,
  total_possible_point, total_score,
  grade_average, percentage_incorrect_answers
FROM hashed
WHERE school_id IS NOT NULL
ORDER BY id, sub_level ASC;
