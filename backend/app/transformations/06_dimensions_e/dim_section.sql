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
--
-- SCOPED-MODE CAVEAT (#10, display-only, ACCEPTED): when a single section_nid is
-- shared across a scoped and a non-scoped assessment, the scoped pass-B staging
-- sees only the scoped item's rows, so the DISTINCT-ON representative (which
-- drives displayed section_name / section_instructors) can differ from what a
-- full rebuild — which sees every item's rows for that section_nid — would pick.
-- This is cosmetic (the KPIs are unaffected) and self-heals on the next full
-- rebuild. The representative pick is intentionally left unchanged; the S2
-- upsert guard below still prevents flipping an UNTOUCHED sibling's row.

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
  JOIN schools sch ON sch.school_id = src.school_id
  WHERE src.user_role_id        = sch.student_role_id
    AND src.section_nid         IS NOT NULL
    AND src.item_id             IS NOT NULL
    AND src.section_name        IS NOT NULL
    AND src.section_instructors IS NOT NULL
    -- section_code is deliberately NOT required: some Schoology exports omit
    -- it entirely (e.g. Central Florida ships every row with a NULL
    -- Section_Code) while still carrying a valid Section_NID + instructors.
    -- Legacy keys this dim on Section_NID, not Section_Code, so requiring a
    -- non-null code wrongly emptied dim_section for those schools and made the
    -- Question Summary Report show every student as "Unassigned".
) sub
ORDER BY school_id, section_nid, section_code, item_id, section_name, section_instructors
ON CONFLICT (school_id, section_nid) DO UPDATE
SET section_code        = EXCLUDED.section_code,
    item_id             = EXCLUDED.item_id,
    section_name        = EXCLUDED.section_name,
    section_instructors = EXCLUDED.section_instructors,
    school_id_csv       = EXCLUDED.school_id_csv
-- SCOPED MODE (S2): dim_section has NO scoped DELETE (its PK spans assessments).
-- A shared section_nid's representative row must only be rewritten when its
-- CURRENT row came from an item that is being replaced this run; otherwise a
-- scoped re-ingest of one item could flip the displayed teacher/section_name on
-- an untouched sibling assessment. Guard the upsert on the EXISTING row's item.
-- Full mode (_scope_assessments empty) → NOT EXISTS InitPlan TRUE → updates every
-- conflict exactly as today.
WHERE (NOT EXISTS (SELECT 1 FROM _scope_assessments)
       OR (dim_section.school_id, dim_section.item_id) IN (SELECT school_id, item_id FROM _scope_items));
