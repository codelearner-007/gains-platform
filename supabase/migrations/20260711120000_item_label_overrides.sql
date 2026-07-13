-- =============================================================================
-- item_label_overrides — per-assessment (item-level) subject/grade/type/name
-- overrides applied at staging, HIGHEST precedence in the label COALESCE chains.
--
-- WHY: subject & grade are derived from the Schoology export FOLDER names. The
-- folder-level tenant overrides (subject_overrides / subject_course_overrides /
-- school_grade_overrides) normalise slicer labels but CANNOT fix a SINGLE
-- assessment that Schoology filed in the wrong course/grade folder (source
-- mis-assignment). Those misfiling corrections were previously applied IN-PLACE
-- to derived tables (fact/dim_subject/dim_item/cubes) and are therefore erased
-- by any pipeline rebuild. This table makes them DURABLE: because
-- subject_id = uuid_6(school, subject, assessment_type, grade, session, item_name)
-- is computed AFTER staging, overriding an item's labels here re-derives the
-- corrected subject_id at every rebuild (and auto-merges label-drift twins,
-- since subject_id excludes item_id).
--
-- Grain: one row per (school_id, item_id). Each Schoology per-section copy is its
-- own item_id, so this grain expresses per-section corrections without a section
-- column. Any NULL override column falls through to the folder overrides / raw.
--
-- Source of truth: docs/audit/data-audit-2026-07/ (REMEDIATION_PLAN + audit_
-- findings) and docs/audit/assessment_misfiling_audit.md. Two classes of rows:
--   * prior misfiling relabels preserved (target = the corrected fact labels
--     that already existed in derived tables before the 2026-07 rebuild);
--   * new misfiles found by the 2026-07 audit (target = section/standard/taker-
--     triangulated correct labels).
-- =============================================================================

CREATE TABLE IF NOT EXISTS item_label_overrides (
  school_id                UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  item_id                  TEXT NOT NULL,
  subject_override         TEXT,
  grade_override           TEXT,
  assessment_type_override TEXT,
  item_name_override       TEXT,
  reason                   TEXT,
  source                   TEXT NOT NULL DEFAULT 'audit-2026-07',
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (school_id, item_id)
);

CREATE INDEX IF NOT EXISTS item_label_overrides_school_idx
  ON item_label_overrides (school_id);
