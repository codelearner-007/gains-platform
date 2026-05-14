-- dim_course — one row per (school_id, course_nid).
-- Notebook line 899 (40_schoology_py_spec.md §4.3):
--   df_dim_course = df_Student_Submissions[
--     ['Course_NID','Course_Name','Course_code','School_ID']
--   ].drop_duplicates().dropna(subset=[...all four...])
--   self.publish(..., primary_key='Course_NID')

INSERT INTO dim_course (
  course_nid, school_id, course_name, course_code, school_id_csv
)
-- DISTINCT ON (school_id, course_nid) so the upsert never sees the same PK
-- twice in one statement (Postgres rejects that with "ON CONFLICT DO UPDATE
-- command cannot affect row a second time"). When a course has multiple
-- (course_name, course_code) variants we keep one deterministic row.
SELECT DISTINCT ON (src.school_id, src.course_nid)
  src.course_nid,
  src.school_id,
  src.course_name,
  src.course_code,
  src.user_school_id AS school_id_csv
FROM stg_student_submission src
WHERE src.course_nid   IS NOT NULL
  AND src.course_name  IS NOT NULL
  AND src.course_code  IS NOT NULL
ORDER BY src.school_id, src.course_nid, src.course_name
ON CONFLICT (school_id, course_nid) DO UPDATE
SET course_name   = EXCLUDED.course_name,
    course_code   = EXCLUDED.course_code,
    school_id_csv = EXCLUDED.school_id_csv;
