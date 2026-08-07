-- dim_subject — DISTINCT (school_id, subject, assessment_type, grade,
-- session, item_name) -> subject_id = uuid_6(...).
-- Notebook line 1168 (40_schoology_py_spec.md §4.7):
--   dim_subject = fact_Student_Submissions[
--     ['Subject_ID','School_ID','Subject','Assessment_type','Grade',
--      'Session','Item_Name']].drop_duplicates().dropna(...)
-- Subject_ID was added at line 913-915:
--   generate_uuid_6(School_ID, Subject, Assessment_type, Grade, Session, Item_Name)
--
-- Calculated columns (per notebook 1170-1175 + 40_schoology_py_spec.md §4.7):
--   grade_sort           = if Grade='Grade K' then 'Grade 0' else Grade
--   grade_no             = right(Grade, 1)
--   show_history_subject = if Grade='Grade 6' AND Subject='History' then 'World History'
--                          if Grade='Grade 7' AND Subject='History' then 'US History'
--                          else Subject

-- TRUNCATE first (not just ON CONFLICT upsert): a relabel/misfiling fix changes
-- subject_id (the hash of the labels), so an upsert-only build would leave the
-- OLD subject_id row behind as a 0-fact phantom card. dim_subject is a pure
-- DISTINCT projection of staging, so a full rebuild is safe and idempotent.
--
-- SCOPED MODE (temp table _scope_assessments non-empty): replace only the
-- touched subject_ids instead of wiping the whole dim. Full mode (both scope
-- temp tables empty) keeps the original TRUNCATE — byte-identical to today.
DO $scope$ BEGIN
  IF EXISTS (SELECT 1 FROM _scope_assessments) THEN
    DELETE FROM dim_subject
    WHERE subject_id IN (SELECT subject_id FROM _scope_assessments);
  ELSE
    TRUNCATE TABLE dim_subject;
  END IF;
END $scope$;

INSERT INTO dim_subject (
  subject_id, school_id, school_id_csv, subject, assessment_type, grade,
  session, item_name, grade_sort, show_history_subject, grade_no
)
SELECT DISTINCT ON (school_id, subject_id)
  uuid_6(
    src.school_id::text,
    src.subject,
    src.assessment_type,
    src.grade,
    src.session,
    src.item_name
  ) AS subject_id,
  src.school_id,
  src.user_school_id AS school_id_csv,
  src.subject,
  src.assessment_type,
  src.grade,
  src.session,
  src.item_name,
  CASE WHEN src.grade = 'Grade K' THEN 'Grade 0' ELSE src.grade END AS grade_sort,
  CASE
    WHEN src.grade = 'Grade 6' AND src.subject = 'History' THEN 'World History'
    WHEN src.grade = 'Grade 7' AND src.subject = 'History' THEN 'US History'
    ELSE src.subject
  END AS show_history_subject,
  RIGHT(src.grade, 1) AS grade_no
FROM stg_student_submission src
JOIN schools sch ON sch.school_id = src.school_id
WHERE src.user_role_id    = sch.student_role_id
  AND src.subject         IS NOT NULL
  AND src.assessment_type IS NOT NULL
  AND src.grade           IS NOT NULL
  AND src.session         IS NOT NULL
  AND src.item_name       IS NOT NULL
  -- SCOPED MODE: only (re)insert the touched subject_ids. In full mode
  -- (_scope_assessments empty) the NOT EXISTS InitPlan is TRUE once and the
  -- filter is a no-op → byte-identical to today. Reuses this file's own
  -- subject_id expression (staging is already override-resolved).
  AND (NOT EXISTS (SELECT 1 FROM _scope_assessments)
       OR uuid_6(
            src.school_id::text,
            src.subject,
            src.assessment_type,
            src.grade,
            src.session,
            src.item_name
          ) IN (SELECT subject_id FROM _scope_assessments))
ORDER BY
  src.school_id,
  uuid_6(src.school_id::text, src.subject, src.assessment_type, src.grade, src.session, src.item_name),
  src.user_school_id NULLS LAST
ON CONFLICT (school_id, subject_id) DO UPDATE
SET school_id_csv        = EXCLUDED.school_id_csv,
    subject              = EXCLUDED.subject,
    assessment_type      = EXCLUDED.assessment_type,
    grade                = EXCLUDED.grade,
    session              = EXCLUDED.session,
    item_name            = EXCLUDED.item_name,
    grade_sort           = EXCLUDED.grade_sort,
    show_history_subject = EXCLUDED.show_history_subject,
    grade_no             = EXCLUDED.grade_no;
