-- =============================================================================
-- Post-fact dimension reconciliation (2026-07 audit, F-C1).
--
-- Runs in the `facts` phase AFTER fact_student_submission.sql. dim_item and
-- dim_subject are built from STAGING (all export vintages), but fact keeps only
-- the latest-export/override-corrected bucket per item. That divergence left:
--   * dim_item.subject_id pointing at a bucket fact abandoned (first-occurrence
--     vs latest-export) -> the assessment is invisible in the dashboard grid
--     even though fact rows exist (orphan subject_ids);
--   * dim_subject rows with 0 fact rows (relabel/prune leftovers) -> phantom
--     0-student report cards.
-- This step makes both agree with fact, durably, every rebuild.
-- =============================================================================

-- (1) Point each dim_item at the subject_id its fact rows actually settled on
-- (the dominant bucket by row count). Items with no fact rows keep their
-- staging subject_id (nothing to reconcile to).
UPDATE dim_item di
SET subject_id = fdom.subject_id
FROM (
  SELECT DISTINCT ON (school_id, item_id) school_id, item_id, subject_id
  FROM (
    SELECT school_id, item_id, subject_id, count(*) AS c
    FROM fact_student_submission
    GROUP BY 1, 2, 3
  ) t
  ORDER BY school_id, item_id, c DESC, subject_id
) fdom
WHERE di.school_id = fdom.school_id
  AND di.item_id = fdom.item_id
  AND di.subject_id IS DISTINCT FROM fdom.subject_id;

-- (2) Drop phantom dim_subject cards: subject_ids with no fact rows AND no cube
-- rows (cubes are rebuilt after this, so 0 fact rows is the authority here).
DELETE FROM dim_subject ds
WHERE NOT EXISTS (
  SELECT 1 FROM fact_student_submission f
  WHERE f.school_id = ds.school_id AND f.subject_id = ds.subject_id
);

-- (3) Canonicalize instructor identity (2026-07 audit, DG-4): 'Sitara Shamsheer'
-- and 'Sitara Qalander' are the same person (co-teaching the same Crestwell
-- classes; Qalander is the current/dominant name). Merge the maiden-name spelling
-- into the current one in the comma-joined section_instructors strings so the
-- teacher filter and by-teacher reports show one identity.
UPDATE dim_item
SET section_instructors = regexp_replace(section_instructors, 'Sitara Shamsheer', 'Sitara Qalander', 'g')
WHERE section_instructors LIKE '%Sitara Shamsheer%';

UPDATE dim_section
SET section_instructors = regexp_replace(section_instructors, 'Sitara Shamsheer', 'Sitara Qalander', 'g')
WHERE section_instructors LIKE '%Sitara Shamsheer%';
