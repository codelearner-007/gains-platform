-- cube_overallperformance_summary — per-(identifier, item_id, item_name,
-- question_id, question_no, standards) totals + averages.
-- Notebook lines 2192-2273 (40_schoology_py_spec.md §7).
--
-- Shape:
--   GROUP BY (school_id, identifier, item_id, item_name, question_id,
--             question_no, standards):
--     total_possible_point = sum(points_possible)
--     total_score          = sum(points_received)
--     grade_average        = sum/sum
--     percentage_incorrect = 1 - grade_average
--   id = sha256(concat_ws(', ', school_id, identifier, item_id, item_name,
--                                question_id, question_no, standards))
--
-- school_id is now an explicit grouping key (no more `MAX(school_id::text)`
-- hack) so multi-tenant data does not blend across schools.
--
-- The notebook joins fact to dim_question_data (per question) to bring
-- question_no + standards (the long-form Standards string) onto each row.
-- We mirror that here. NULL standards -> 'Other' (notebook 2249).

TRUNCATE TABLE cube_overallperformance_summary;

INSERT INTO cube_overallperformance_summary (
  id, school_id, identifier, item_id, item_name,
  question_id, question_no, standards,
  total_possible_point, total_score,
  grade_average, percentage_incorrect_answers
)
WITH joined AS (
  SELECT
    f.school_id,
    f.identifier,
    f.item_id,
    f.item_name,
    f.question_id,
    qd.question_no,
    -- Notebook applies Standards->'Other' for null/blank.
    CASE
      WHEN qd.standards IS NULL OR qd.standards IN ('', 'null') THEN 'Other'
      ELSE qd.standards
    END                                AS standards,
    f.points_possible,
    f.points_received
  FROM fact_student_submission f
  LEFT JOIN (
    -- DISTINCT (school_id, question_id) version of dim_question_data so we
    -- attach exactly one (question_no, standards) per question. If a question
    -- has multiple rows, ORDER BY identifier NULLS LAST picks the row with
    -- a real identifier first.
    SELECT DISTINCT ON (school_id, question_id)
      school_id, question_id, question_no, standards, identifier
    FROM dim_question_data
    WHERE question_id IS NOT NULL
    ORDER BY school_id, question_id, identifier NULLS LAST
  ) qd
    ON qd.school_id   = f.school_id
   AND qd.question_id = f.question_id
),
rolled AS (
  SELECT
    school_id,
    identifier,
    item_id,
    item_name,
    question_id,
    question_no,
    standards,
    SUM(points_possible)        AS total_possible_point,
    SUM(points_received)        AS total_score,
    SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                                AS grade_average,
    1 - SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                                AS percentage_incorrect_answers
  FROM joined
  GROUP BY school_id, identifier, item_id, item_name, question_id,
           question_no, standards
)
SELECT
  encode(digest(
    CONCAT_WS(', ',
      COALESCE(school_id::text, 'DEFAULT_SCHOOL_ID'),
      COALESCE(identifier,  'DEFAULT_IDENTIFIER'),
      COALESCE(item_id,     'DEFAULT_ITEM_ID'),
      COALESCE(item_name,   'DEFAULT_ITEM_NAME'),
      COALESCE(question_id, 'DEFAULT_QUESTION_ID'),
      COALESCE(question_no, 'DEFAULT_QUESTION_NO'),
      COALESCE(standards,   'DEFAULT_STANDARDS')
    ),
    'sha256'
  ), 'hex')                          AS id,
  school_id,
  identifier,
  item_id,
  item_name,
  question_id,
  question_no,
  standards,
  total_possible_point,
  total_score,
  grade_average,
  percentage_incorrect_answers
FROM rolled
WHERE school_id IS NOT NULL;
