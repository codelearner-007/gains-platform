-- dim_school — one row per (UUID school_id).
-- Notebook line 851 (40_schoology_py_spec.md §4.1):
--   df_dim_school = df_Student_Submissions[['School_ID','School_Name']]
--                     .drop_duplicates().dropna(subset=['School_ID','School_Name'])
--   self.publish(..., primary_key='School_ID')
--
-- Our PK is the UUID school_id (FK to schools). school_id_csv preserves the
-- original CSV value for audit.

INSERT INTO dim_school (school_id, school_id_csv, school_name)
SELECT DISTINCT
  src.school_id,
  src.user_school_id  AS school_id_csv,
  src.user_school_name AS school_name
FROM stg_student_submission src
WHERE src.user_school_id   IS NOT NULL
  AND src.user_school_name IS NOT NULL
ON CONFLICT (school_id) DO UPDATE
SET school_id_csv = EXCLUDED.school_id_csv,
    school_name   = EXCLUDED.school_name;
