-- dim_section — DISTINCT (section_code, item_id, section_nid, section_name,
-- section_instructors, school_id).
-- Notebook line 1141 (40_schoology_py_spec.md §4.7):
--   df_dim_section = fact_Student_Submissions[
--     ['Section_Code','Item_ID','Section_NID','Section_Name',
--      'Section_Instructors','School_ID']
--   ].drop_duplicates().dropna(subset=[...])
--   self.publish(..., primary_key='Section_NID')
--
-- We build it from stg_student_submission (the rows that drive the fact)
-- restricted to user_role_id = 286170 — the same filter the notebook applies
-- to fact_Student_Submissions.
--
-- Because (school_id, section_nid) is the dim PK but the underlying tuples
-- can differ across rows that share section_nid (e.g. one section_nid carrying
-- two section_codes via a co-teacher pair), we deduplicate via DISTINCT ON
-- with a deterministic ORDER BY for repeatability.

INSERT INTO dim_section (
  section_nid, school_id, section_code, item_id,
  section_name, section_instructors, school_id_csv
)
SELECT DISTINCT ON (school_id, section_nid)
  section_nid,
  school_id,
  section_code,
  item_id,
  section_name,
  section_instructors,
  school_id_csv
FROM (
  SELECT
    src.section_nid,
    src.school_id,
    src.section_code,
    src.item_id,
    src.section_name,
    src.section_instructors,
    src.user_school_id AS school_id_csv
  FROM stg_student_submission src
  WHERE src.user_role_id        = '286170'
    AND src.section_nid         IS NOT NULL
    AND src.section_code        IS NOT NULL
    AND src.item_id             IS NOT NULL
    AND src.section_name        IS NOT NULL
    AND src.section_instructors IS NOT NULL
) sub
ORDER BY school_id, section_nid, section_code, item_id, section_name, section_instructors
ON CONFLICT (school_id, section_nid) DO UPDATE
SET section_code        = EXCLUDED.section_code,
    item_id             = EXCLUDED.item_id,
    section_name        = EXCLUDED.section_name,
    section_instructors = EXCLUDED.section_instructors,
    school_id_csv       = EXCLUDED.school_id_csv;
