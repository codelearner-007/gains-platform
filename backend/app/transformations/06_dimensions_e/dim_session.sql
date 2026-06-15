-- dim_session — DISTINCT (school_id, session) -> session_id = uuid_2(...).
-- Notebook line 1148 (40_schoology_py_spec.md §4.7):
--   dim_session = fact_Student_Submissions[
--     ['School_ID','Session']].drop_duplicates()
--   dim_session = dim_session.withColumn(
--     "session_ID", generate_uuid_2(dim_session['School_ID'], dim_session['Session']))
--   dim_session = dim_session.dropna(subset=["Session_ID","School_ID","Session"])

INSERT INTO dim_session (session_id, school_id, school_id_csv, session)
SELECT DISTINCT ON (school_id, session_id)
  uuid_2(src.school_id::text, src.session) AS session_id,
  src.school_id,
  src.user_school_id AS school_id_csv,
  src.session
FROM stg_student_submission src
JOIN schools sch ON sch.school_id = src.school_id
WHERE src.user_role_id = sch.student_role_id
  AND src.session      IS NOT NULL
ORDER BY src.school_id, uuid_2(src.school_id::text, src.session), src.user_school_id NULLS LAST
ON CONFLICT (school_id, session_id) DO UPDATE
SET school_id_csv = EXCLUDED.school_id_csv,
    session       = EXCLUDED.session;
