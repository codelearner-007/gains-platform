-- Leading-subject_id index on fact_student_submission for the scoped transform.
--
-- The scoped DELETE re-folds only the touched subjects and runs
--   DELETE FROM fact_student_submission WHERE subject_id IN (SELECT ... )
-- (and the roster/coverage read checks probe the pre-delete fact by subject_id).
-- fact already carries (school_id, subject_id) and (school_id, subject_id,
-- user_uid) composites, but every existing index LEADS with school_id, so none
-- of them can serve a predicate keyed on subject_id alone — the planner falls
-- back to a full sequential scan of the (large) fact table on each scoped run.
--
-- This adds the missing leading-subject_id btree. Parity-safe: an index changes
-- no rows, so EMPTY-scope / full-mode output is byte-identical. Idempotent via
-- IF NOT EXISTS so it is safe to re-apply on the local box and the clone.
CREATE INDEX IF NOT EXISTS fact_student_submission_subject_idx
  ON fact_student_submission (subject_id);
