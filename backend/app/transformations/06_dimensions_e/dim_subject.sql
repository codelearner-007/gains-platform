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
