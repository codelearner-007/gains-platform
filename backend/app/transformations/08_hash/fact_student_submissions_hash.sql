-- fact_student_submissions_hash — same shape as fact_student_submission but
-- with user_name swapped for the StudentName_Hash. Notebook line 1314.
--
-- The schema (migration 080) created this table with `LIKE
-- fact_student_submission INCLUDING DEFAULTS INCLUDING CONSTRAINTS` plus an
-- extra `student_name_hash TEXT` column. We populate user_name with the hash
-- value AND the dedicated student_name_hash column with the same value (for
-- explicit access in queries that need the hash).
--
-- TRUNCATE+INSERT idempotency: pure derivation from fact + dim_student_hash.

TRUNCATE TABLE fact_student_submissions_hash;

INSERT INTO fact_student_submissions_hash (
  user_id_ques_id_stand,
  school_id,
  user_uid,
  user_name,
  user_role_id,
  school_id_csv,
  course_nid,
  section_nid,
  section_code,
  item_id,
  item_name,
  first_access,
  latest_attempt,
  total_time,
  submission_grade,
  submission,
  question_id,
  session,
  assessment_type,
  subject,
  grade,
  section,
  position_number,
  sub_question,
  answer_submission,
  correct_answer,
  points_received,
  points_possible,
  user_id_ques_id,
  grade_id,
  assessment_id,
  subject_id,
  strand_id,
  standard,
  identifier,
  student_name_hash
)
SELECT
  f.user_id_ques_id_stand,
  f.school_id,
  f.user_uid,
  -- The hashed name replaces user_name. Fall back to the original when no
  -- hash row exists (e.g. user_uid was NULL on the fact row).
  COALESCE(sh.student_name_hash, f.user_name) AS user_name,
  f.user_role_id,
  f.school_id_csv,
  f.course_nid,
  f.section_nid,
  f.section_code,
  f.item_id,
  f.item_name,
  f.first_access,
  f.latest_attempt,
  f.total_time,
  f.submission_grade,
  f.submission,
  f.question_id,
  f.session,
  f.assessment_type,
  f.subject,
  f.grade,
  f.section,
  f.position_number,
  f.sub_question,
  f.answer_submission,
  f.correct_answer,
  f.points_received,
  f.points_possible,
  f.user_id_ques_id,
  f.grade_id,
  f.assessment_id,
  f.subject_id,
  f.strand_id,
  f.standard,
  f.identifier,
  sh.student_name_hash
FROM fact_student_submission f
LEFT JOIN dim_student_hash sh
  ON sh.school_id = f.school_id
 AND sh.user_uid  = f.user_uid;
