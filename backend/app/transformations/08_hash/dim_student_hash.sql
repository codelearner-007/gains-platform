-- dim_student_hash — pseudonymized student labels per (school_id, user_uid).
-- Notebook lines 1295-1320 (40_schoology_py_spec.md §7 "Pseudonymisation tables").
--
-- Same pattern as dim_section_hash: ROW_NUMBER partitioned by school_id,
-- ordered by user_uid. Labels are "Student_Name 0", "Student_Name 1", ...
-- Source is fact_student_submission so we cover every student that landed a
-- submission row (there is no fact->dim foreign key on user_uid because
-- dim_student is empty in Phase 2 — Phase 7 will populate it).
--
-- TRUNCATE+INSERT idempotency: deterministic sort produces stable hashes.

TRUNCATE TABLE dim_student_hash;

INSERT INTO dim_student_hash (
  school_id, user_uid, user_name, student_name_hash
)
SELECT
  school_id,
  user_uid,
  user_name,
  'Student_Name ' || (
    ROW_NUMBER() OVER (
      PARTITION BY school_id
      ORDER BY user_uid
    ) - 1
  )::text AS student_name_hash
FROM (
  -- DISTINCT ON (school_id, user_uid) ensures one row per student even when
  -- user_name varies across submissions (otherwise the PK would collide).
  SELECT DISTINCT ON (f.school_id, f.user_uid)
    f.school_id,
    f.user_uid,
    f.user_name
  FROM fact_student_submission f
  WHERE f.user_uid IS NOT NULL
  ORDER BY f.school_id, f.user_uid, f.user_name
) t;
