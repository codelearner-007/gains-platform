-- dim_section_hash — pseudonymized teacher labels per (school_id, section_nid).
-- Notebook lines 1295-1320 (40_schoology_py_spec.md §7 "Pseudonymisation tables").
--
-- Spark uses monotonically_increasing_id(); Postgres equivalent is ROW_NUMBER
-- partitioned by school_id (so two tenants don't share a global hash sequence)
-- and ordered by section_nid for deterministic re-runs. Labels are
-- "Teacher_Name 0", "Teacher_Name 1", ... per the notebook string format.
--
-- TRUNCATE+INSERT idempotency: hash labels are derived from a deterministic
-- sort, so the same input always produces the same hash. Re-running emits an
-- identical table.

TRUNCATE TABLE dim_section_hash;

INSERT INTO dim_section_hash (
  school_id, section_nid, section_instructors, teacher_name_hash
)
SELECT
  school_id,
  section_nid,
  section_instructors,
  'Teacher_Name ' || (
    ROW_NUMBER() OVER (
      PARTITION BY school_id
      ORDER BY section_nid, COALESCE(section_instructors, '')
    ) - 1
  )::text AS teacher_name_hash
FROM (
  SELECT DISTINCT
    school_id,
    section_nid,
    section_instructors
  FROM dim_section
  WHERE section_nid IS NOT NULL
) t;
