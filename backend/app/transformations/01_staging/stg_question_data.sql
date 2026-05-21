-- Staging: raw_question_data -> stg_question_data.
-- The raw table is already wide-to-long melted (Standards*, Answer_Breakdown*)
-- by the Phase 1 ingestion parser. This staging step trims strings, applies
-- the same subject overrides as stg_student_submission for consistency, and
-- normalizes empty strings to NULL.
--
-- Tenant overrides applied here:
--   1. subject_overrides            (grade + subject_match -> subject_override)
--   2. subject_course_overrides     (course_name regex)  -- N/A: question_data
--                                   has no course_name column.
--
-- Notebook reference: question_data is loaded at line 798 then receives
-- subject overrides via the same mapping table (notebook 232-321).

TRUNCATE TABLE stg_question_data;

INSERT INTO stg_question_data (
  school_id, item_id, item_name, question_id, associated_question_id,
  total_points, question_type, question, position_number, sub_question,
  correct_answer, correctly_answered, most_points_earned, least_points_earned,
  average_points_earned, standards_val, session, assessment_type, subject,
  grade, section, file_name, question_no
)
SELECT
  s.school_id,
  NULLIF(TRIM(rqd.item_id), ''),
  NULLIF(TRIM(rqd.item_name), ''),
  NULLIF(TRIM(rqd.question_id), ''),
  NULLIF(TRIM(rqd.associated_question_id), ''),
  rqd.total_points,
  NULLIF(TRIM(rqd.question_type), ''),
  rqd.question,
  NULLIF(TRIM(rqd.position_number), ''),
  NULLIF(TRIM(rqd.sub_question), ''),
  NULLIF(TRIM(rqd.correct_answer), ''),
  rqd.correctly_answered,
  rqd.most_points_earned,
  rqd.least_points_earned,
  rqd.average_points_earned,
  NULLIF(TRIM(rqd.standards_val), ''),
  NULLIF(TRIM(rqd.session), ''),
  NULLIF(TRIM(rqd.assessment_type), ''),
  COALESCE(so.subject_override, NULLIF(TRIM(rqd.subject), '')) AS subject,
  -- Grade remap also applies here (notebook 985 — Grade 9-12 -> Regular 9–12)
  COALESCE(go.grade_override, NULLIF(TRIM(rqd.grade), '')) AS grade,
  NULLIF(TRIM(rqd.section), ''),
  NULLIF(TRIM(rqd.file_name), ''),
  NULLIF(TRIM(rqd.question_no), '')
FROM raw_question_data rqd
JOIN schools s ON s.school_id = rqd.school_id
LEFT JOIN subject_overrides so
  ON so.school_id     = s.school_id
 AND so.grade         = rqd.grade
 AND so.subject_match = rqd.subject
LEFT JOIN LATERAL (
  SELECT grade_override
  FROM school_grade_overrides x
  WHERE x.school_id = s.school_id
    AND rqd.grade = ANY(x.grade_match)
  ORDER BY x.override_id
  LIMIT 1
) go ON TRUE;
