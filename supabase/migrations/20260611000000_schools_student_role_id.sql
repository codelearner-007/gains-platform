-- Add a per-school student User-Role-ID to the schools table.
--
-- Schoology assigns a distinct numeric "User Role ID" to the Student role in
-- EACH building. Athenian uses 286170, but the other backup schools differ
-- (Central Florida Prep 320939, South Prep 925819, Crestwell 927486,
-- Brightview 927606). The transformation SQL filters dim_student / dim_item /
-- fact_student_submission / the derived dims to "students only" by this id; a
-- single hardcoded 286170 zeroed out every non-Athenian school.
--
-- Default 286170 keeps Athenian's existing rows byte-identical after backfill.

ALTER TABLE schools
  ADD COLUMN IF NOT EXISTS student_role_id TEXT NOT NULL DEFAULT '286170';
