-- SCOPED-TRANSFORM NOTE: this file now references the session-local _scope_items
-- temp table (created by run_all). A manual psql replay must first create the 3
-- _scope_* temp tables EMPTY, else this file errors on the missing table.
--
-- scope_prune_orphans.sql — SCOPED-ONLY orphan sweep (runs in the `facts` phase
-- AFTER validate_no_cross_band.sql).
--
-- item_id CHURNS on re-ingest: a re-scraped assessment arrives under NEW item_ids
-- while the fact DELETE keys on the STABLE subject_id. The upsert dims
-- (dim_item / dim_unit_lesson / dim_question_data are keyed on (school_id,item_id);
-- dim_section keeps one representative item_id per (school_id,section_nid)) would
-- otherwise retain the OLD item_ids as orphans after the churn. This step deletes
-- exactly those orphans, and ONLY for items the batch actually re-ingested
-- (membership in _scope_items) that have NO fact rows left — so a fact-less
-- parquet/legacy dim row that was never in this batch is never touched.
--
-- The whole file is guarded on EXISTS(_scope_items): in a full rebuild every dim
-- is truncated/rebuilt from scratch, _scope_items is empty, and this is a NO-OP.

DO $prune$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM _scope_items) THEN
    RETURN;  -- full rebuild: nothing scoped to prune
  END IF;

  -- dim_item: re-ingested (school_id,item_id) with no surviving fact rows.
  DELETE FROM dim_item di
  WHERE (di.school_id, di.item_id) IN (SELECT school_id, item_id FROM _scope_items)
    AND NOT EXISTS (
      SELECT 1 FROM fact_student_submission f
      WHERE f.school_id = di.school_id AND f.item_id = di.item_id
    );

  -- dim_unit_lesson: same (school_id,item_id) grain as dim_item.
  DELETE FROM dim_unit_lesson dul
  WHERE (dul.school_id, dul.item_id) IN (SELECT school_id, item_id FROM _scope_items)
    AND NOT EXISTS (
      SELECT 1 FROM fact_student_submission f
      WHERE f.school_id = dul.school_id AND f.item_id = dul.item_id
    );

  -- dim_question_data: same (school_id,item_id) grain.
  DELETE FROM dim_question_data dqd
  WHERE (dqd.school_id, dqd.item_id) IN (SELECT school_id, item_id FROM _scope_items)
    AND NOT EXISTS (
      SELECT 1 FROM fact_student_submission f
      WHERE f.school_id = dqd.school_id AND f.item_id = dqd.item_id
    );

  -- dim_section: PK is (school_id,section_nid) and it holds one representative
  -- item_id. Drop the section only when its representative item is being
  -- re-ingested AND no fact remains for (school_id,section_nid).
  DELETE FROM dim_section dsec
  WHERE (dsec.school_id, dsec.item_id) IN (SELECT school_id, item_id FROM _scope_items)
    AND NOT EXISTS (
      SELECT 1 FROM fact_student_submission f
      WHERE f.school_id = dsec.school_id AND f.section_nid = dsec.section_nid
    );
END
$prune$;
