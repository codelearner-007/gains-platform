-- Covering index for the dashboard "Total Students" distinct-headcount query
-- (get_school_total_students). The query joins fact_student_submission to
-- dim_subject on (school_id, subject_id) and counts DISTINCT user_uid under the
-- session/subject/grade/assessment_type filters. Without a covering index the
-- whole-school (no-grade) scope heap-scans all ~1.2M per-school fact rows
-- (~130k buffer reads, ~900ms). This index lets Postgres satisfy the count with
-- an INDEX ONLY SCAN (~5k buffers), keeping the correct fact-based headcount
-- (the GAI-20 distinct-count decision) while removing the bottleneck.
--
-- Additive + idempotent. The fact table is bulk-loaded (no hot writes in prod),
-- so the write-amplification cost is negligible.
CREATE INDEX IF NOT EXISTS fss_school_subject_user_covering_idx
  ON public.fact_student_submission (school_id, subject_id, user_uid);
