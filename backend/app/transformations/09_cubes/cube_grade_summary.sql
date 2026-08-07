-- cube_grade_summary — per-(school, subject, item) grade rollup.
-- Notebook lines 1337-1366 (40_schoology_py_spec.md §7).
--
-- Shape:
--   per_user: GROUP BY (school_id, subject_id, user_uid, item_id)
--             grade_average = sum(points_received) / sum(points_possible)
--   rolled:   ROLLUP over (school_id, subject_id, item_id)
--             grade_average                = AVG(grade_average)
--             percentage_incorrect_answers = 1 - AVG(grade_average)
--             grade_min                    = MIN(grade_average)
--             grade_max                    = MAX(grade_average)
--   id = sha256(coalesce(school_id,'DEFAULT_SCHOOL_ID') ||
--               coalesce(subject_id,'DEFAULT_SUBJECT_ID') ||
--               coalesce(item_id,'DEFAULT_ITEM_ID'))
--
-- TRUNCATE+INSERT idempotency: deterministic GROUPING SETS + sha256.

-- Scoped rebuild: every persisted row is school-rooted — each GROUPING SET is
-- anchored on school_id and the () grand-total row is dropped by the final
-- WHERE school_id IS NOT NULL — and the AVG/MIN/MAX aggregates are within-school.
-- So deleting + recomputing only the touched schools' slices is byte-identical
-- to a full rebuild for those schools while leaving untouched schools intact.
-- Empty scope (full rebuild) falls through to the whole-table DELETE —
-- byte-identical to today.
DO $scope$ BEGIN
  IF EXISTS (SELECT 1 FROM _scope_assessments) THEN
    DELETE FROM cube_grade_summary
    WHERE school_id IN (SELECT DISTINCT school_id FROM _scope_assessments);
  ELSE
    DELETE FROM cube_grade_summary;
  END IF;
END $scope$;

INSERT INTO cube_grade_summary (
  id, school_id, school_id_csv, subject_id, item_id,
  grade_average, percentage_incorrect_answers, grade_min, grade_max
)
WITH per_user AS (
  SELECT
    school_id,
    school_id_csv,
    subject_id,
    user_uid,
    item_id,
    SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0) AS grade_average
  FROM fact_student_submission
  -- Scoped rebuild: restrict the fact scan to the touched schools so the rollup
  -- recomputes only those slices. No-op when _scope_assessments is empty
  -- (full rebuild) — NOT EXISTS InitPlan TRUE, byte-identical to today.
  WHERE (NOT EXISTS (SELECT 1 FROM _scope_assessments)
         OR school_id IN (SELECT DISTINCT school_id FROM _scope_assessments))
  GROUP BY school_id, school_id_csv, subject_id, user_uid, item_id
),
rolled AS (
  SELECT
    school_id,
    -- school_id_csv is informational, not a grouping key; we surface MAX so
    -- it survives the GROUPING SETS rollup.
    MAX(school_id_csv)                AS school_id_csv,
    subject_id,
    item_id,
    AVG(grade_average)                AS grade_average,
    1 - AVG(grade_average)            AS percentage_incorrect_answers,
    MIN(grade_average)                AS grade_min,
    MAX(grade_average)                AS grade_max,
    GROUPING(school_id) + GROUPING(subject_id) + GROUPING(item_id) AS sub_level
  FROM per_user
  GROUP BY GROUPING SETS (
    (school_id, subject_id, item_id),
    (school_id, subject_id),
    (school_id),
    ()
  )
),
hashed AS (
  SELECT
    encode(digest(
      COALESCE(school_id::text, 'DEFAULT_SCHOOL_ID') ||
      COALESCE(subject_id,      'DEFAULT_SUBJECT_ID') ||
      COALESCE(item_id,         'DEFAULT_ITEM_ID'),
      'sha256'
    ), 'hex')                            AS id,
    school_id, school_id_csv, subject_id, item_id,
    grade_average, percentage_incorrect_answers, grade_min, grade_max,
    sub_level
  FROM rolled
)
-- DISTINCT ON (id): collapses identical-hash rows from rollup levels that
-- coincide with real-NULL data. Prefer the deepest grouping (sub_level=0).
SELECT DISTINCT ON (id)
  id, school_id, school_id_csv, subject_id, item_id,
  grade_average, percentage_incorrect_answers, grade_min, grade_max
FROM hashed
WHERE school_id IS NOT NULL
ORDER BY id, sub_level ASC;
