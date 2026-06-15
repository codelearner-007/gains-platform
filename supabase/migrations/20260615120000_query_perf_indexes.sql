-- Request-time query performance indexes (audit 2026-06-15).
--
-- All are pure access-path changes — they NEVER alter query results. Each was
-- profiled on a full-data school (Athenian: 1.65M facts, 1.13M cube_user_summary
-- rows) where the target query was doing a full-table heap scan + large sort.
--
-- On a fresh DB these tables are empty so the build is instant; on a populated
-- DB build them with CREATE INDEX CONCURRENTLY out-of-band if writers are live.

-- 1) YTD longitudinal cells (section×user×standard matrix): COVERING index.
--    The key columns (school_id+session equality prefix, then the DISTINCT ON
--    ordering) let Unique consume the index with no Sort; the INCLUDE payload
--    makes the dedup scan index-only (Heap Fetches: 0) instead of ~650MB of
--    random heap reads. Paired with the query change that drops the unused
--    COUNT(DISTINCT item_id) + ORDER BY so the GROUP BY hash-aggregates.
--    (~8s → ~2s on a full-year school.)
CREATE INDEX IF NOT EXISTS fact_student_submission_ytd_dedup_idx
  ON public.fact_student_submission
     (school_id, session, user_uid, item_id, question_id, position_number, standard)
  INCLUDE (user_name, section_nid, points_received, points_possible);

-- 2) YTD "standard units" (DISTINCT item_id, item_name per school+session): push
--    the session filter into the index + cover item_name for an index-only scan
--    instead of a ~947ms heap scan dropping ~640k wrong-session rows. (~1.2s → ~0.35s.)
CREATE INDEX IF NOT EXISTS fact_student_submission_school_session_item_name_idx
  ON public.fact_student_submission (school_id, session) INCLUDE (item_id, item_name);

-- 3) YTD school-meta (DISTINCT over the 7-tuple): exact leading keys → index-only
--    scan + Unique instead of a heap scan + 896k-row HashAggregate. (~710ms → ~130ms.)
CREATE INDEX IF NOT EXISTS idx_cus_ytd_meta
  ON public.cube_user_summary
     (school_id, item_id, subject, grade, session, assessment_type, item_name);

-- 4) School "total assessments" / total-students (COUNT(DISTINCT item_id) by
--    session [+section]): covering index → index-only scan, eliminates the
--    ~48k-buffer (~375MB) heap read that dropped ~895k rows. (~733ms → ~200ms.)
CREATE INDEX IF NOT EXISTS cube_user_summary_school_session_item_section_idx
  ON public.cube_user_summary (school_id, session, item_id, section_nid);

-- 5) YTD "tests taken" (COUNT(DISTINCT item_id) per user by session): per-user
--    grouping pushed into the index, session filter as an index cond. Complements
--    the get_ytd_longitudinal_tests_taken rewrite that now reads this cube.
CREATE INDEX IF NOT EXISTS cube_user_summary_school_session_user_item_idx
  ON public.cube_user_summary (school_id, session, user_uid, item_id);
