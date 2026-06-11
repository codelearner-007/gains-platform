-- dim_grade — DISTINCT (school_id, grade) -> grade_id = uuid_2(school_id, grade).
-- Notebook line 1158 (40_schoology_py_spec.md §4.7):
--   dim_grade = fact_Student_Submissions[
--     ['Grade_ID','School_ID','Grade']].drop_duplicates().dropna(...)
-- Grade_ID was added at line 909-910:
--   generate_uuid_2(df['School_ID'], df['Grade'])

INSERT INTO dim_grade (grade_id, school_id, school_id_csv, grade)
SELECT DISTINCT ON (school_id, grade_id)
  uuid_2(src.school_id::text, src.grade) AS grade_id,
  src.school_id,
  src.user_school_id AS school_id_csv,
  src.grade
FROM stg_student_submission src
JOIN schools sch ON sch.school_id = src.school_id
WHERE src.user_role_id = sch.student_role_id
  AND src.grade        IS NOT NULL
ORDER BY src.school_id, uuid_2(src.school_id::text, src.grade), src.user_school_id NULLS LAST
ON CONFLICT (school_id, grade_id) DO UPDATE
SET school_id_csv = EXCLUDED.school_id_csv,
    grade         = EXCLUDED.grade;
