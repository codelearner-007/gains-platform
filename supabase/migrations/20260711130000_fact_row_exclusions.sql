-- =============================================================================
-- fact_row_exclusions — durable per-(item, spurious-label) row exclusions applied
-- at the fact build (07_facts/fact_student_submission.sql base CTE).
--
-- WHY: some Schoology exports contain SPURIOUS PARTIAL DUPLICATES of an
-- assessment under a wrong course FOLDER (e.g. a Grade-2 Math test re-exported
-- into a HS English folder, carrying a partial-question copy of the same
-- students). They render a phantom cross-band report card. The duplicate shares
-- the same section_nid as the real rows (only the folder-derived subject/grade
-- differ), and latest-export-wins does NOT collapse it (different question
-- subset). Prior manual fixes DELETED these rows; this makes that durable.
--
-- Grain: (school_id, item_id, subject, grade) — drop the rows of an item that
-- carry the spurious (subject, grade) label. Reusable by Phase-4 twin/duplicate
-- cleanup.
-- =============================================================================

CREATE TABLE IF NOT EXISTS fact_row_exclusions (
  school_id  UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  item_id    TEXT NOT NULL,
  subject    TEXT NOT NULL,
  grade      TEXT NOT NULL,
  reason     TEXT,
  source     TEXT NOT NULL DEFAULT 'audit-2026-07',
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  PRIMARY KEY (school_id, item_id, subject, grade)
);

CREATE INDEX IF NOT EXISTS fact_row_exclusions_school_item_idx
  ON fact_row_exclusions (school_id, item_id);
