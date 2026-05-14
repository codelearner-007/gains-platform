-- Staging: raw_submission_summary -> stg_submission_summary.
-- Pass-through with school_id (UUID) resolved from raw rows. No tenant
-- overrides apply to submission summary.
--
-- Notebook reference: section 4 — `df_Submission_Summary = oea.load(...)`
-- (line 798).

TRUNCATE TABLE stg_submission_summary;

INSERT INTO stg_submission_summary (
  school_id, schoology_id, first_name, last_name, unique_id_csv, job_title,
  gradebook_grade, submission_no, submission_score, question_label, question_score
)
SELECT
  rss.school_id,
  NULLIF(TRIM(rss.schoology_id), ''),
  NULLIF(TRIM(rss.first_name), ''),
  NULLIF(TRIM(rss.last_name), ''),
  NULLIF(TRIM(rss.unique_id_csv), ''),
  NULLIF(TRIM(rss.job_title), ''),
  NULLIF(TRIM(rss.gradebook_grade), ''),
  rss.submission_no,
  rss.submission_score,
  NULLIF(TRIM(rss.question_label), ''),
  rss.question_score
FROM raw_submission_summary rss;
