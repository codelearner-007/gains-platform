-- dim_assessment_type — DISTINCT (school_id, assessment_type) ->
-- assessment_id = uuid_2(school_id, assessment_type).
-- Notebook line 1163 (40_schoology_py_spec.md §4.7):
--   dim_assessment_type = fact_Student_Submissions[
--     ['Assessment_ID','School_ID','Assessment_type']].drop_duplicates().dropna(...)
-- Assessment_ID was added at line 911-912:
--   generate_uuid_2(df['School_ID'], df['Assessment_type'])

INSERT INTO dim_assessment_type (
  assessment_id, school_id, school_id_csv, assessment_type
)
SELECT DISTINCT ON (school_id, assessment_id)
  uuid_2(src.school_id::text, src.assessment_type) AS assessment_id,
  src.school_id,
  src.user_school_id AS school_id_csv,
  src.assessment_type
FROM stg_student_submission src
WHERE src.user_role_id     = '286170'
  AND src.assessment_type  IS NOT NULL
ORDER BY src.school_id, uuid_2(src.school_id::text, src.assessment_type), src.user_school_id NULLS LAST
ON CONFLICT (school_id, assessment_id) DO UPDATE
SET school_id_csv   = EXCLUDED.school_id_csv,
    assessment_type = EXCLUDED.assessment_type;
