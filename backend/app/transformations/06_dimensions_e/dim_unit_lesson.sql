-- dim_unit_lesson — DISTINCT (item_id, item_name, school_id).
-- Notebook line 1135 (40_schoology_py_spec.md §4.7):
--   dim_unit_lesson = df_Student_Submissions[
--     ['Item_ID','Item_Name','School_ID']].drop_duplicates()
--   self.publish(..., primary_key='Item_ID')

-- DISTINCT ON (school_id, item_id) collapses to ONE row per item: a plain
-- DISTINCT would keep multiple rows when the same item has differing
-- item_name / user_school_id across submissions (seen once >1 school is
-- ingested), which then collide on the (school_id, item_id) conflict key in a
-- single INSERT → CardinalityViolation. ORDER BY makes the pick deterministic.
INSERT INTO dim_unit_lesson (item_id, school_id, item_name, school_id_csv)
SELECT DISTINCT ON (src.school_id, src.item_id)
  src.item_id,
  src.school_id,
  src.item_name,
  src.user_school_id AS school_id_csv
FROM stg_student_submission src
WHERE src.item_id   IS NOT NULL
  AND src.item_name IS NOT NULL
ORDER BY src.school_id, src.item_id,
         src.item_name NULLS LAST, src.user_school_id NULLS LAST
ON CONFLICT (school_id, item_id) DO UPDATE
SET item_name     = EXCLUDED.item_name,
    school_id_csv = EXCLUDED.school_id_csv;
