-- dim_item — one row per (school_id, item_id).
-- Notebook lines 904-944 (40_schoology_py_spec.md §4.4):
--   1. Compute synthetic columns on the working student-submissions copy:
--        Subject_ID    = uuid_6(School_ID, Subject, Assessment_type, Grade, Session, Item_Name)
--        assessment_date = date_format(Latest_Attempt, "MM/dd/yyyy")
--   2. Restrict to students (User_Role_ID == 286170) per notebook 924-927.
--   3. drop_duplicates + dropna on Item_ID, Subject_ID, Section_Name,
--      Section_Instructors, Item_Type, Item_Name, School_ID, assessment_date.
--   4. Window: PARTITION BY (Item_ID, Subject_ID, Section_Name,
--      Section_Instructors, Item_Type, Item_Name, School_ID)
--      ORDER BY assessment_date ASC -> keep ROW_NUMBER = 1
--      (the FIRST occurrence per item — earliest assessment date).
--   5. publish primary_key='Item_ID'.

INSERT INTO dim_item (
  item_id, school_id, subject_id, item_type, item_name,
  school_id_csv, section_name, section_instructors, assessment_date
)
WITH ss_keys AS (
  -- Add Subject_ID + assessment_date_str on top of staging rows.
  -- Per the notebook this is computed inside the working
  -- df_Student_Submissions copy used for fact_Student_Submissions; we
  -- reproduce that here for the dim build.
  SELECT
    src.school_id,
    src.user_school_id,
    src.user_role_id,
    src.item_id,
    src.item_name,
    src.item_type,
    src.section_name,
    src.section_instructors,
    src.latest_attempt,
    -- Subject_ID per notebook line 921 (40_schoology_py_spec.md §4.4 line 290):
    --   generate_uuid_6(School_ID, Subject, Assessment_type, Grade, Session, Item_Name)
    -- All inputs cast to text; School_ID is the UUID stringified to match the
    -- legacy notebook (which used the same string). NULL inputs flow through
    -- concat_ws as separator-only and produce a deterministic hash.
    uuid_6(
      src.school_id::text,
      src.subject,
      src.assessment_type,
      src.grade,
      src.session,
      src.item_name
    ) AS subject_id,
    -- MM/DD/YYYY string format (notebook line 920) preserved for the dedupe
    -- order key, then cast to DATE on final SELECT.
    to_char(src.latest_attempt, 'MM/DD/YYYY') AS assessment_date_str
  FROM stg_student_submission src
  WHERE src.user_role_id = '286170'  -- students only (notebook 924-927)
),
distinct_items AS (
  SELECT DISTINCT
    item_id, subject_id, assessment_date_str,
    section_name, section_instructors, item_type, item_name,
    school_id, user_school_id
  FROM ss_keys
  WHERE item_id              IS NOT NULL
    AND subject_id           IS NOT NULL
    AND section_name         IS NOT NULL
    AND section_instructors  IS NOT NULL
    AND item_type            IS NOT NULL
    AND item_name            IS NOT NULL
    AND assessment_date_str  IS NOT NULL
),
ranked AS (
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY item_id, subject_id, section_name, section_instructors,
                   item_type, item_name, school_id
      ORDER BY to_date(assessment_date_str, 'MM/DD/YYYY') ASC
    ) AS rn
  FROM distinct_items
),
first_per_partition AS (
  SELECT
    item_id,
    school_id,
    subject_id,
    item_type,
    item_name,
    user_school_id,
    section_name,
    section_instructors,
    assessment_date_str
  FROM ranked
  WHERE rn = 1
)
-- Final dedupe by primary key (school_id, item_id) so the upsert cannot hit
-- the same conflict target twice in a single statement (which Postgres rejects
-- with "ON CONFLICT DO UPDATE command cannot affect row a second time"). The
-- earliest assessment_date wins, matching the notebook's "first occurrence".
SELECT DISTINCT ON (school_id, item_id)
  item_id,
  school_id,
  subject_id,
  item_type,
  item_name,
  user_school_id AS school_id_csv,
  section_name,
  section_instructors,
  to_date(assessment_date_str, 'MM/DD/YYYY') AS assessment_date
FROM first_per_partition
ORDER BY school_id, item_id, to_date(assessment_date_str, 'MM/DD/YYYY') ASC
ON CONFLICT (school_id, item_id) DO UPDATE
SET subject_id          = EXCLUDED.subject_id,
    item_type           = EXCLUDED.item_type,
    item_name           = EXCLUDED.item_name,
    school_id_csv       = EXCLUDED.school_id_csv,
    section_name        = EXCLUDED.section_name,
    section_instructors = EXCLUDED.section_instructors,
    assessment_date     = EXCLUDED.assessment_date;
