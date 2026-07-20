-- validate_no_cross_band.sql — build-time guard against cross-band mis-files.
--
-- Durable prevention for the cross-band phantom class (audit F-C2). After the
-- base-CTE exclusions and dim_reconcile settle labels, every item_id must map
-- to exactly ONE (grade, subject_id) label-set. A single item_id spanning 2+
-- grades or 2+ subject_ids means an export was mis-filed — a partial-question
-- copy re-filed under a wrong subject/grade folder (same section_nid) — which
-- renders a phantom report card (e.g. a "1 student / 0%" band).
--
-- This asserts the invariant and FAILS THE BUILD, naming the offending items,
-- so the operator adds a fact_row_exclusions (or subject/grade override) seed
-- row for the spurious label bucket and rebuilds — BEFORE cubes are built on
-- bad data. It reads only; it moves no reported number.
--
-- Do NOT "resolve" a violation by adding grade to the latest_export
-- PARTITION BY: the twin rows share the same (user, question, position,
-- submission) tuples, so partitioning by grade makes BOTH survive and
-- COMPLETES the phantom. The correct, durable fix is an exclusion/override
-- row for the spurious bucket. If a violation is ever a legitimate dual-band
-- item, whitelist it explicitly after confirming with the school.

DO $crossband$
DECLARE
  v_count integer;
  v_items text;
BEGIN
  SELECT count(*),
         string_agg(
           school_id::text || '/' || item_id
             || ' (grades=' || n_grades || ', subject_ids=' || n_subjects || ')',
           '; ' ORDER BY school_id::text, item_id)
    INTO v_count, v_items
  FROM (
    SELECT school_id,
           item_id,
           count(DISTINCT grade)      AS n_grades,
           count(DISTINCT subject_id) AS n_subjects
    FROM fact_student_submission
    GROUP BY school_id, item_id
    HAVING count(DISTINCT grade) > 1
        OR count(DISTINCT subject_id) > 1
  ) offenders;

  IF v_count > 0 THEN
    RAISE EXCEPTION
      'cross-band mis-file: % item(s) span multiple grade/subject buckets in fact_student_submission. Offenders: %. Add a fact_row_exclusions (or subject/grade override) seed row for the spurious label bucket, then rebuild. Never add grade to the latest_export partition (it completes the phantom).',
      v_count, v_items;
  END IF;
END
$crossband$;
