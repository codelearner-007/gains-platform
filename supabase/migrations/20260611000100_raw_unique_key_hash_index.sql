-- Bound the raw-table dedup UNIQUE index to a fixed-size hash of unique_key.
--
-- raw_*.unique_key is a concatenation of free-text CSV fields (answer text,
-- correct answer, standards label, …). Some Schoology questions embed base64
-- image data URIs in their answer options, producing unique_key values >> 8 KB.
-- A plain B-tree UNIQUE (school_id, source_file_hash, unique_key) then rejects
-- the row with "index row requires N bytes, maximum size is 8191", silently
-- dropping whole assessments at ingest (and previously poisoning the batch).
--
-- Fix: dedup on md5(unique_key) instead of the raw text. md5 is deterministic,
-- so the dedup semantics are identical (same key -> same hash -> same conflict),
-- but every index entry is now a fixed 32-byte hex string. unique_key itself is
-- KEPT as a plain column for traceability; only the index expression changes.
-- The matching INSERT ... ON CONFLICT inference clauses are updated in
-- backend/app/jobs/ingest_schoology.py to target (school_id, source_file_hash,
-- md5(unique_key)).

ALTER TABLE raw_submission_summary
  DROP CONSTRAINT IF EXISTS raw_submission_summary_school_id_source_file_hash_unique_ke_key;
CREATE UNIQUE INDEX IF NOT EXISTS raw_submission_summary_dedup_uidx
  ON raw_submission_summary (school_id, source_file_hash, md5(unique_key));

ALTER TABLE raw_student_submission
  DROP CONSTRAINT IF EXISTS raw_student_submission_school_id_source_file_hash_unique_ke_key;
CREATE UNIQUE INDEX IF NOT EXISTS raw_student_submission_dedup_uidx
  ON raw_student_submission (school_id, source_file_hash, md5(unique_key));

ALTER TABLE raw_question_data
  DROP CONSTRAINT IF EXISTS raw_question_data_school_id_source_file_hash_unique_key_key;
CREATE UNIQUE INDEX IF NOT EXISTS raw_question_data_dedup_uidx
  ON raw_question_data (school_id, source_file_hash, md5(unique_key));

-- Same overflow class on dim_question_data: its PRIMARY KEY (school_id, qkey)
-- includes correct_answer in qkey, and a base64-image answer makes qkey exceed
-- the composite-btree limit (2704 bytes), failing the whole dim build. Swap the
-- PK for a UNIQUE index on (school_id, md5(qkey)). Dedup grain is unchanged
-- (md5 is deterministic 1:1 with qkey); qkey itself is KEPT as a plain column
-- (cubes still project it). No FK references dim_question_data, so dropping the
-- formal PRIMARY KEY is safe. The matching INSERT ... ON CONFLICT inference in
-- 04_dimensions_c/dim_question_data.sql is updated to (school_id, md5(qkey)).
ALTER TABLE dim_question_data
  DROP CONSTRAINT IF EXISTS dim_question_data_pkey;
CREATE UNIQUE INDEX IF NOT EXISTS dim_question_data_pk_uidx
  ON dim_question_data (school_id, md5(qkey));

-- fact_student_submission (and its hash twin) key on user_id_ques_id_stand,
-- which concatenates answer_submission — again a base64 image can blow past the
-- single-column btree limit (8191 bytes). Swap the PK for a UNIQUE index on
-- md5(user_id_ques_id_stand). Dedup grain identical; the column is KEPT (reports
-- and the hash twin still read it). No FK references either fact table. The
-- INSERT ... ON CONFLICT in 07_facts/fact_student_submission.sql is updated to
-- md5(user_id_ques_id_stand); the hash twin is a pure TRUNCATE+INSERT (no
-- conflict clause) so only its index needs swapping.
ALTER TABLE fact_student_submission
  DROP CONSTRAINT IF EXISTS fact_student_submission_pkey;
CREATE UNIQUE INDEX IF NOT EXISTS fact_student_submission_pk_uidx
  ON fact_student_submission (md5(user_id_ques_id_stand));

ALTER TABLE fact_student_submissions_hash
  DROP CONSTRAINT IF EXISTS fact_student_submissions_hash_pkey;
CREATE UNIQUE INDEX IF NOT EXISTS fact_student_submissions_hash_pk_uidx
  ON fact_student_submissions_hash (md5(user_id_ques_id_stand));
