-- Per-item twin of cube_question_summary_overall.
--
-- cube_question_summary_overall is grained by (school_id, subject_id, ukey, …)
-- and subject_id = uuid_6(…, item_name) — so every SECTION of a multi-section
-- assessment shares the subject_id and gets POOLED into one row. The per-
-- assessment Strand/Standard "% Correct" rollups read it and therefore showed a
-- cross-section average (a teacher's report mixing other sections' students).
--
-- This twin replays cqso's EXACT grade computation with item_id added to the
-- grain, so per-item reports can read a section-scoped grade. Populated by
-- app/transformations/09_cubes/cube_question_summary_overall_by_item.sql
-- (TRUNCATE + INSERT, run with the other cubes). The schema mirrors the cqso
-- `totals` columns plus item_id. No surrogate `id`: the grain carries nullable
-- columns (ukey/position_number can be NULL), so a composite PK is not viable;
-- the table is a TRUNCATE+INSERT rollup read by (school_id, item_id).
--
-- This migration MUST be applied before any backend that queries the table
-- (get_strand_rollup_for_item / get_standard_rollup_for_item) is deployed.

CREATE TABLE cube_question_summary_overall_by_item (
  school_id              UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  subject_id             TEXT,
  item_id                TEXT,
  ukey                   TEXT,
  question_no            TEXT,
  position_number        TEXT,
  correct_answer         TEXT,
  standards              TEXT,
  total_possible_point   NUMERIC,
  total_score            NUMERIC,
  grade_average          NUMERIC
);

CREATE INDEX cube_qso_by_item_item_idx
  ON cube_question_summary_overall_by_item (school_id, item_id);
CREATE INDEX cube_qso_by_item_subject_idx
  ON cube_question_summary_overall_by_item (school_id, subject_id);
