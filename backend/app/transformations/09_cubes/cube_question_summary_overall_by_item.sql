-- cube_question_summary_overall_by_item — the per-QUESTION-CONTENT grade rollup,
-- IDENTICAL to cube_question_summary_overall's `totals` computation but grained
-- by item_id as well, so per-item reports can read a section-scoped grade.
--
-- WHY: cube_question_summary_overall is grained by (school_id, subject_id, ukey,
-- question_no, question, position_number, correct_answer, standard) and
-- subject_id = uuid_6(..., item_name) — so every SECTION of one assessment
-- (same item_name, different item_id) shares the subject_id and gets POOLED into
-- one row. The per-assessment Strand/Standard "% Correct" rollups read cqso by
-- subject_id and therefore showed a cross-section average (a teacher's report
-- mixing other sections' students). cube_question_summary lacks the latest-
-- attempt + multi-select MAX-collapse + per-(question-content) grain that cqso's
-- grade_average uses, so it cannot reproduce cqso exactly; this table replays
-- cqso's EXACT chain with item_id added.
--
-- INVARIANT (proven before use): aggregating this table back over item_id
-- (GROUP BY school_id, subject_id, ukey, ... ; SUM/SUM) reproduces
-- cube_question_summary_overall's grade_average row-for-row. So a single-section
-- assessment (subject_id → one item) is byte-identical to cqso (no baseline
-- move); a multi-section assessment is correctly split per section.

CREATE TABLE IF NOT EXISTS cube_question_summary_overall_by_item (
  school_id              uuid,
  subject_id             text,
  item_id                text,
  ukey                   text,
  question_no            text,
  position_number        text,
  correct_answer         text,
  standards              text,
  total_possible_point   numeric,
  total_score            numeric,
  grade_average          numeric
);

TRUNCATE TABLE cube_question_summary_overall_by_item;

INSERT INTO cube_question_summary_overall_by_item (
  school_id, subject_id, item_id, ukey, question_no, position_number,
  correct_answer, standards, total_possible_point, total_score, grade_average
)
WITH ranked AS (
  -- Latest-attempt filter — IDENTICAL to cube_question_summary_overall.sql.
  SELECT
    f.*,
    ROW_NUMBER() OVER (
      PARTITION BY f.section_nid, f.session, f.grade, f.subject,
                   f.assessment_type, f.school_id, f.user_uid, f.item_id,
                   f.question_id
      ORDER BY f.submission DESC NULLS LAST,
               EXTRACT(EPOCH FROM f.total_time) DESC NULLS LAST,
               f.user_id_ques_id_stand
    ) AS rn
  FROM fact_student_submission f
),
latest AS (
  SELECT * FROM ranked WHERE rn = 1
),
latest_with_hash AS (
  SELECT
    l.school_id,
    l.user_uid,
    l.subject_id,
    l.item_id,
    l.position_number,
    COALESCE(l.correct_answer, 'n/a') AS correct_answer,
    l.points_possible,
    l.points_received,
    l.standard,
    qd.question,
    qd.question_no,
    qd.ukey
  FROM latest l
  LEFT JOIN (
    SELECT DISTINCT ON (school_id, question_id, position_number)
      school_id, question_id, position_number, ukey, question_no, question
    FROM dim_question_data
    WHERE question_id IS NOT NULL
    ORDER BY school_id, question_id, position_number, ukey NULLS LAST
  ) qd
    ON qd.school_id   = l.school_id
   AND qd.question_id = l.question_id
   AND COALESCE(qd.position_number, '__NULL__')
       = COALESCE(l.position_number, '__NULL__')
)
-- totals — IDENTICAL to cqso's `totals` CTE, with item_id added to BOTH the
-- per-student collapse and the output grain.
SELECT
  school_id,
  subject_id,
  item_id,
  ukey,
  question_no,
  position_number,
  correct_answer,
  CASE WHEN standard IS NULL OR standard IN ('', 'null') THEN 'Other'
       ELSE standard END                                     AS standards,
  SUM(points_possible)                                       AS total_possible_point,
  SUM(points_received)                                       AS total_score,
  SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0) AS grade_average
FROM (
  SELECT
    school_id, subject_id, item_id, ukey, question_no, question,
    position_number, correct_answer, standard, user_uid,
    MAX(points_received) AS points_received,
    MAX(points_possible) AS points_possible
  FROM latest_with_hash
  GROUP BY school_id, subject_id, item_id, ukey, question_no, question,
           position_number, correct_answer, standard, user_uid
) per_student
WHERE school_id IS NOT NULL
GROUP BY school_id, subject_id, item_id, ukey, question_no, question,
         position_number, correct_answer, standard;

CREATE INDEX IF NOT EXISTS ix_cqso_by_item_item
  ON cube_question_summary_overall_by_item (school_id, item_id);
