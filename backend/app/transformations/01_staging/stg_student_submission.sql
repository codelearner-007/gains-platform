-- Staging: raw_student_submission -> stg_student_submission.
-- Resolves school_id (UUID) from user_school_id (TEXT in CSV) via the
-- schools.schoology_school_id key, then applies four tenant overrides per
-- Schoology_py.ipynb lines 232-413 (40_schoology_py_spec.md §3 "Tenant
-- subject/grade overrides"):
--
--   1. subject_overrides            (grade + subject_match -> subject_override)
--   2. subject_course_overrides     (course_name regex     -> subject_override)
--   3. school_grade_overrides       (grade ANY(grade_match)-> grade_override)
--   4. teacher_pair_overrides       (section_instructors   -> primary_teacher)
--
-- The notebook applies role-id filtering AT DIM TIME, NOT here — staging keeps
-- every role so dim_student/teacher/parent each filter the same upstream rows.

TRUNCATE TABLE stg_student_submission;

INSERT INTO stg_student_submission (
  school_id, user_uid, username, last_name, first_name, user_role_id,
  user_school_id, user_school_name, course_nid, course_name, course_code,
  section_nid, section_name, section_code, section_instructors,
  item_type, item_id, item_name, first_access, latest_attempt, total_time,
  submission_grade, submission, question_id, associated_question_id,
  question_type, question, position_number, sub_question, answer_submission,
  correct_answer, points_received, points_possible, session, assessment_type,
  subject, grade, section, file_name
)
SELECT
  s.school_id,
  NULLIF(TRIM(rss.user_uid), ''),
  NULLIF(TRIM(rss.username), ''),
  NULLIF(TRIM(rss.last_name), ''),
  NULLIF(TRIM(rss.first_name), ''),
  NULLIF(TRIM(rss.user_role_id), ''),
  NULLIF(TRIM(rss.user_school_id), ''),
  NULLIF(TRIM(rss.user_school_name), ''),
  NULLIF(TRIM(rss.course_nid), ''),
  NULLIF(TRIM(rss.course_name), ''),
  NULLIF(TRIM(rss.course_code), ''),
  NULLIF(TRIM(rss.section_nid), ''),
  NULLIF(TRIM(rss.section_name), ''),
  NULLIF(TRIM(rss.section_code), ''),
  -- Override 4: teacher pair -> primary teacher (notebook 367-413)
  COALESCE(tp.primary_teacher, NULLIF(TRIM(rss.section_instructors), '')) AS section_instructors,
  NULLIF(TRIM(rss.item_type), ''),
  NULLIF(TRIM(rss.item_id), ''),
  NULLIF(TRIM(rss.item_name), ''),
  rss.first_access,
  rss.latest_attempt,
  rss.total_time,
  rss.submission_grade,
  rss.submission,
  NULLIF(TRIM(rss.question_id), ''),
  NULLIF(TRIM(rss.associated_question_id), ''),
  NULLIF(TRIM(rss.question_type), ''),
  rss.question,
  NULLIF(TRIM(rss.position_number), ''),
  NULLIF(TRIM(rss.sub_question), ''),
  rss.answer_submission,
  NULLIF(TRIM(rss.correct_answer), ''),
  rss.points_received,
  rss.points_possible,
  NULLIF(TRIM(rss.session), ''),
  -- assessment_type: item override wins (twin-merge to dominant type), else
  -- whitespace-normalized raw (F-F1: collapses 'Lesson  Assessments' double-space
  -- + other stray whitespace so slicer variants don't fragment reports).
  COALESCE(ilo.assessment_type_override,
           NULLIF(regexp_replace(btrim(rss.assessment_type), '\s+', ' ', 'g'), '')),
  -- Override resolution order (notebook semantics):
  --   item_label_overrides wins (per-assessment misfiling correction, 2026-07)
  --   else subject_course_overrides (regex match on course_name)
  --   else subject_overrides     (exact match on grade + subject)
  --   else raw subject
  COALESCE(ilo.subject_override, sco.subject_override, so.subject_override, NULLIF(TRIM(rss.subject), '')) AS subject,
  -- Override 3: grade — per-item misfiling correction wins, then grade remap
  -- (notebook 985 — Grade 9-12 -> Regular 9–12)
  COALESCE(ilo.grade_override, go.grade_override, NULLIF(TRIM(rss.grade), '')) AS grade,
  NULLIF(TRIM(rss.section), ''),
  NULLIF(TRIM(rss.file_name), '')
FROM raw_student_submission rss
-- Resolve the REAL school from the CSV's "User School ID" (raw.user_school_id)
-- against schools.schoology_school_id — NOT the stamped raw.school_id. This lets
-- a single mixed/whole backup tree ingest each row to its correct school. The
-- stamped raw.school_id stays only as the raw idempotency key.
JOIN schools s
  ON s.schoology_school_id = NULLIF(TRIM(rss.user_school_id), '')
-- Override 0 (highest precedence): per-assessment misfiling correction. Keyed on
-- (school_id, item_id); each Schoology per-section copy is its own item_id.
LEFT JOIN item_label_overrides ilo
  ON ilo.school_id = s.school_id
 AND ilo.item_id   = NULLIF(TRIM(rss.item_id), '')
LEFT JOIN subject_overrides so
  ON so.school_id     = s.school_id
 AND so.grade         = rss.grade
 AND so.subject_match = rss.subject
LEFT JOIN LATERAL (
  -- Override 2: take the FIRST regex match by override_id (legacy: first hit wins)
  SELECT subject_override
  FROM subject_course_overrides x
  WHERE x.school_id = s.school_id
    AND rss.course_name ~ x.course_name_match_regex
  ORDER BY x.override_id
  LIMIT 1
) sco ON TRUE
LEFT JOIN LATERAL (
  -- Override 3: grade is ANY of grade_match[]
  SELECT grade_override
  FROM school_grade_overrides x
  WHERE x.school_id = s.school_id
    AND rss.grade = ANY(x.grade_match)
  ORDER BY x.override_id
  LIMIT 1
) go ON TRUE
LEFT JOIN teacher_pair_overrides tp
  ON tp.school_id    = s.school_id
 AND tp.pair_pattern = rss.section_instructors
-- Drop the 2025-26 placeholder pair. The Schoology folder name literally reads
-- "remove grade level" / "No grade level" — an explicit instruction to discard
-- these non-instructional rows (no override maps them to a real subject/grade).
WHERE NULLIF(TRIM(rss.grade), '')   IS DISTINCT FROM 'remove grade level'
  AND NULLIF(TRIM(rss.subject), '') IS DISTINCT FROM 'No grade level';
