-- fact_student_submission — 35-column grain row, one per
-- (school_id, user_uid, question_id, position_number, answer_submission,
-- points_possible, submission, standard).
-- Notebook §5 (lines 1180-1294, see 40_schoology_py_spec.md §5).
--
-- Build steps:
--   1. Filter stg_student_submission to user_role_id = '286170' (students only,
--      notebook line 1199).
--   2. Pre-INSERT dedupe via ROW_NUMBER over the 8-part key columns. The
--      notebook uses ingested_at-DESC; stg has no ingested_at because raw is
--      already deduped on (school_id, source_file_hash, unique_key). We use a
--      deterministic NULL-resilient ordering instead so re-runs are stable.
--   3. Compute synthetic per-row IDs:
--      User_id_ques_id = user_uid || '-' || question_id
--      User_Name       = first_name || ' ' || last_name
--      Qkey            = session || assessment_type || subject || grade ||
--                        question_id  (raw concat, no separator — notebook
--                        line 1241; the column does not feed the notebook's
--                        dim_question_data.qkey which uses concat with
--                        separators per dim_question_data §4.5)
--      Grade_ID        = uuid_2(school_id::text, grade)
--      Assessment_ID   = uuid_2(school_id::text, assessment_type)
--      Subject_ID      = uuid_6(school_id::text, subject, assessment_type,
--                                grade, session, item_name)
--   4. Joins (notebook lines 1255-1268):
--      a. dim_question_data (DISTINCT question_id, standard) -> attaches the
--         long-form Standard string carried on the question.
--      b. dim_standard via substring match (`q.standard ILIKE '%' ||
--         schoology_standard || '%'`) -> identifier.
--      c. dim_strand by identifier -> strand_id.
--   5. Synthetic 8-part PK (notebook line 1270):
--      User_id_ques_id_stand = coalesce(school_id,'DEFAULT_SCHOOLID') || '-' ||
--                              coalesce(user_uid,'DEFAULT_USER')      || '-' ||
--                              coalesce(question_id,'DEFAULT_QID')    || '-' ||
--                              coalesce(position_number,'DEFAULT_POS')|| '-' ||
--                              coalesce(answer_submission,'DEFAULT_ANSWER_SUBMISSION') || '-' ||
--                              coalesce(points_possible::text,'DEFAULT_POINTS_REC') || '-' ||
--                              coalesce(submission::text,'Submission') || '-' ||
--                              coalesce(identifier,'DEFAULT_STANDARD')
--   ON CONFLICT (user_id_ques_id_stand) DO UPDATE.
--
-- The substring join can produce >1 row per stg-row when the same `standard`
-- string contains multiple registered schoology_standard codes; the dedupe by
-- user_id_ques_id_stand ON CONFLICT handles it (last writer wins). The
-- DISTINCT ON in the deduped CTE guarantees the dedupe is deterministic on
-- the 8-part key irrespective of dim_question_data.standard rowcount.

-- TRUNCATE + INSERT (full rebuild). The runner always rebuilds from the full
-- stg set, and the `latest_export` CTE PRUNES stale re-export rows (so the row
-- set SHRINKS vs a prior build). A pure upsert would leave the pruned rows
-- behind as orphans, defeating the latest-export collapse — so we truncate
-- first, exactly like the staging and cube builds. The ON CONFLICT clause
-- remains as an in-run safety net for the synthetic PK.
TRUNCATE TABLE fact_student_submission;

INSERT INTO fact_student_submission (
  user_id_ques_id_stand,
  school_id,
  user_uid,
  user_name,
  user_role_id,
  school_id_csv,
  course_nid,
  section_nid,
  section_code,
  item_id,
  item_name,
  first_access,
  latest_attempt,
  total_time,
  submission_grade,
  submission,
  question_id,
  session,
  assessment_type,
  subject,
  grade,
  section,
  position_number,
  sub_question,
  answer_submission,
  correct_answer,
  points_received,
  points_possible,
  user_id_ques_id,
  grade_id,
  assessment_id,
  subject_id,
  strand_id,
  standard,
  identifier
)
WITH base AS (
  -- Filter to students (notebook 1199).
  SELECT
    src.school_id,
    src.user_uid,
    src.first_name,
    src.last_name,
    src.user_role_id,
    src.user_school_id,
    src.course_nid,
    src.section_nid,
    src.section_code,
    src.item_id,
    src.item_name,
    src.first_access,
    src.latest_attempt,
    src.total_time,
    src.submission_grade,
    src.submission,
    src.question_id,
    src.session,
    src.assessment_type,
    src.subject,
    src.grade,
    src.section,
    src.position_number,
    src.sub_question,
    src.answer_submission,
    src.correct_answer,
    src.points_received,
    src.points_possible,
    src.file_name
  FROM stg_student_submission src
  -- students only (notebook 1199); per-school role via schools.student_role_id
  JOIN schools sch ON sch.school_id = src.school_id
  WHERE src.user_role_id = sch.student_role_id
),
latest_export AS (
  -- LATEST-EXPORT-WINS (legacy parity, Schoology_py.ipynb build_fact_tables
  -- rundate-DESC window). The Schoology backup ACCUMULATES every re-export of
  -- an assessment: raw_student_submission is append-only and each re-export is
  -- a distinct dated CSV, so a single (student, question, attempt) cell can
  -- carry rows from many export files. When a teacher regrades, a LATER export
  -- supersedes an earlier one — e.g. the same submission shows
  --   2025-09-19 export: 'a. People started now.'        -> 0 pts
  --   2025-10-07 export: 'b. People started in the past' -> 1 pt
  -- Legacy ran incrementally so only the newest export's row reached the fact
  -- (verified: legacy Cube_Question_Summary shows exactly ONE row per student
  -- for this question = the latest 'b'/1pt). A full rebuild over the whole
  -- export history does NOT self-collapse (the 8-part PK keeps answer_submission
  -- + points, so the 'a' and 'b' rows fall in different partitions and both
  -- survive, making per-student scores non-deterministic). So we explicitly
  -- keep only the rows from the NEWEST export per response slot.
  --
  -- Grain EXCLUDES answer_submission/points (the things a regrade changes) but
  -- KEEPS submission/position_number/sub_question, so legitimate multi-select
  -- (many option rows within ONE export), multi-attempt, and multi-part rows
  -- are all preserved — they share the winning export's timestamp.
  -- export_ts is parsed from the dated export filename
  -- (...-YYYY-MM-DD-HHMMSS.csv). Rows with no parseable date (e.g. parquet
  -- direct-loads with no file_name) have a NULL max for the slot and are kept
  -- in full (no export ordering available).
  SELECT *
  FROM (
    SELECT
      b.*,
      MAX(b.export_ts) OVER (
        PARTITION BY b.school_id, b.user_uid, b.item_id, b.question_id,
                     b.position_number, b.sub_question, b.submission
      ) AS max_export_ts
    FROM (
      SELECT
        base.*,
        to_timestamp(
          substring(base.file_name FROM '(\d{4}-\d{2}-\d{2}-\d{6})'),
          'YYYY-MM-DD-HH24MISS'
        ) AS export_ts
      FROM base
    ) b
  ) w
  WHERE w.max_export_ts IS NULL
     OR w.export_ts = w.max_export_ts
),
deduped AS (
  -- Pre-INSERT dedupe (notebook lines 1185-1192). Partition columns are the
  -- 8 components of the synthetic PK MINUS submission/points_possible (which
  -- we treat as the latest measurement). Order by submission DESC then
  -- points_received DESC NULLS LAST so the highest-grade row wins on tie.
  SELECT *,
    ROW_NUMBER() OVER (
      PARTITION BY school_id, user_uid, question_id, position_number,
                   answer_submission
      ORDER BY submission DESC NULLS LAST,
               points_received DESC NULLS LAST,
               points_possible DESC NULLS LAST
    ) AS rn
  FROM latest_export
),
qd_standard AS (
  -- DISTINCT (question_id, standard) — notebook line 1255-1257.
  SELECT DISTINCT question_id, standard
  FROM dim_question_data
  WHERE question_id IS NOT NULL
),
joined AS (
  SELECT
    d.*,
    qd.standard AS std,
    ds.identifier AS ident,
    dst.strand_id AS sid
  FROM deduped d
  LEFT JOIN qd_standard qd
    ON qd.question_id = d.question_id
  -- Exact-equality identifier match — see
  -- `.hermes/report-parity/pipeline-audit-2026-05-18.md §B1`. Originally
  -- `qd.standard ILIKE '%' || ds.schoology_standard || '%'` which had the
  -- same prefix-collision problem as `dim_question_data.sql` (and produced
  -- 2 spurious wrong-substring identifiers for item 8359960427). All 12
  -- distinct schoology codes in the audited corpus are exact matches against
  -- `dim_standard.schoology_standard`; non-match category labels like
  -- `Social Studies` correctly resolve to NULL identifier.
  --
  -- The seed `dim_standard.csv` contains a small number of rows where two
  -- distinct identifier UUIDs carry the same schoology_standard (e.g. both
  -- `3cd52b67…` and `3cdd2b67…` map `MA.912.AR.3.1`). Those are CSV
  -- pollution: the second UUID's other cpalms aliases (e.g. `AR.3.10`)
  -- belong to an unrelated standard. LATERAL pins the join to one
  -- identifier per (schoology_standard) — the lexically smallest — so the
  -- fact row count stays at one per (submission, question, standard)
  -- rather than fanning out by the seed-CSV multiplicity.
  LEFT JOIN LATERAL (
    SELECT identifier
    FROM dim_standard
    WHERE schoology_standard IS NOT NULL
      AND qd.standard         IS NOT NULL
      AND schoology_standard = qd.standard
    ORDER BY identifier
    LIMIT 1
  ) ds ON TRUE
  LEFT JOIN dim_strand dst
    ON dst.identifier = ds.identifier
  WHERE d.rn = 1
),
final_dedupe AS (
  -- Word-boundary join (after §B1) yields exactly one identifier per
  -- (question_id, standard) row, but multiple distinct STANDARDS can still
  -- share an identifier (e.g. `MA.912.AR.3.1` and `AI.MA.912.AR.3.1` both
  -- map to `3cd52b67…`). Including `std` in the dedupe key preserves every
  -- distinct (question, identifier, standard) triple, so downstream cubes
  -- never blindly drop a standard alias.
  -- See `.hermes/report-parity/pipeline-audit-2026-05-18.md §B4`.
  SELECT DISTINCT ON (
    COALESCE(school_id::text, 'DEFAULT_SCHOOLID')          || '-' ||
    COALESCE(user_uid, 'DEFAULT_USER')                     || '-' ||
    COALESCE(question_id, 'DEFAULT_QID')                   || '-' ||
    COALESCE(position_number, 'DEFAULT_POS')               || '-' ||
    COALESCE(answer_submission, 'DEFAULT_ANSWER_SUBMISSION')|| '-' ||
    COALESCE(points_possible::text, 'DEFAULT_POINTS_REC')  || '-' ||
    COALESCE(submission::text, 'Submission')               || '-' ||
    COALESCE(ident, 'DEFAULT_STANDARD')                    || '-' ||
    COALESCE(std,   'DEFAULT_STANDARD_TEXT')
  )
    school_id, user_uid, first_name, last_name, user_role_id, user_school_id,
    course_nid, section_nid, section_code, item_id, item_name, first_access,
    latest_attempt, total_time, submission_grade, submission, question_id,
    session, assessment_type, subject, grade, section,
    position_number, sub_question, answer_submission, correct_answer,
    points_received, points_possible, std, ident, sid
  FROM joined
  ORDER BY
    COALESCE(school_id::text, 'DEFAULT_SCHOOLID')          || '-' ||
    COALESCE(user_uid, 'DEFAULT_USER')                     || '-' ||
    COALESCE(question_id, 'DEFAULT_QID')                   || '-' ||
    COALESCE(position_number, 'DEFAULT_POS')               || '-' ||
    COALESCE(answer_submission, 'DEFAULT_ANSWER_SUBMISSION')|| '-' ||
    COALESCE(points_possible::text, 'DEFAULT_POINTS_REC')  || '-' ||
    COALESCE(submission::text, 'Submission')               || '-' ||
    COALESCE(ident, 'DEFAULT_STANDARD')                    || '-' ||
    COALESCE(std,   'DEFAULT_STANDARD_TEXT'),
    ident NULLS LAST,
    sid   NULLS LAST,
    std   NULLS LAST
)
SELECT
  -- Synthetic 9-part PK — extends the notebook's 8-part PK with `std` so
  -- distinct standard aliases that share an identifier (e.g. `MA.912.AR.3.1`
  -- and `AI.MA.912.AR.3.1` both `3cd52b67…`) survive as separate rows.
  -- Matches the dedupe key above.
  -- See `.hermes/report-parity/pipeline-audit-2026-05-18.md §B4`.
  COALESCE(school_id::text, 'DEFAULT_SCHOOLID')          || '-' ||
  COALESCE(user_uid, 'DEFAULT_USER')                     || '-' ||
  COALESCE(question_id, 'DEFAULT_QID')                   || '-' ||
  COALESCE(position_number, 'DEFAULT_POS')               || '-' ||
  COALESCE(answer_submission, 'DEFAULT_ANSWER_SUBMISSION')|| '-' ||
  COALESCE(points_possible::text, 'DEFAULT_POINTS_REC')  || '-' ||
  COALESCE(submission::text, 'Submission')               || '-' ||
  COALESCE(ident, 'DEFAULT_STANDARD')                    || '-' ||
  COALESCE(std,   'DEFAULT_STANDARD_TEXT')               AS user_id_ques_id_stand,
  school_id,
  user_uid,
  -- User_Name = First_Name + ' ' + Last_Name (notebook 1235). NULL fallback
  -- to either side becoming NULL means the concat returns NULL when both are
  -- NULL; we COALESCE each piece to '' so a partial name still surfaces.
  NULLIF(TRIM(CONCAT(COALESCE(first_name, ''), ' ', COALESCE(last_name, ''))), '')
                                                          AS user_name,
  user_role_id,
  user_school_id                                          AS school_id_csv,
  course_nid,
  section_nid,
  section_code,
  item_id,
  item_name,
  first_access,
  latest_attempt,
  total_time,
  submission_grade,
  submission,
  question_id,
  session,
  assessment_type,
  subject,
  grade,
  section,
  position_number,
  sub_question,
  answer_submission,
  correct_answer,
  points_received,
  points_possible,
  -- User_id_ques_id (notebook 1230)
  COALESCE(user_uid, '') || '-' || COALESCE(question_id, '')
                                                          AS user_id_ques_id,
  uuid_2(school_id::text, grade)                          AS grade_id,
  uuid_2(school_id::text, assessment_type)                AS assessment_id,
  uuid_6(
    school_id::text, subject, assessment_type, grade, session, item_name
  )                                                       AS subject_id,
  sid                                                     AS strand_id,
  std                                                     AS standard,
  ident                                                   AS identifier
FROM final_dedupe
-- Conflict target is the md5(user_id_ques_id_stand) UNIQUE index (migration
-- 20260611000100): the raw key concatenates answer_submission and can exceed the
-- btree limit when an answer embeds a base64 image. Semantics are unchanged.
ON CONFLICT (md5(user_id_ques_id_stand)) DO UPDATE
SET school_id        = EXCLUDED.school_id,
    user_uid         = EXCLUDED.user_uid,
    user_name        = EXCLUDED.user_name,
    user_role_id     = EXCLUDED.user_role_id,
    school_id_csv    = EXCLUDED.school_id_csv,
    course_nid       = EXCLUDED.course_nid,
    section_nid      = EXCLUDED.section_nid,
    section_code     = EXCLUDED.section_code,
    item_id          = EXCLUDED.item_id,
    item_name        = EXCLUDED.item_name,
    first_access     = EXCLUDED.first_access,
    latest_attempt   = EXCLUDED.latest_attempt,
    total_time       = EXCLUDED.total_time,
    submission_grade = EXCLUDED.submission_grade,
    submission       = EXCLUDED.submission,
    question_id      = EXCLUDED.question_id,
    session          = EXCLUDED.session,
    assessment_type  = EXCLUDED.assessment_type,
    subject          = EXCLUDED.subject,
    grade            = EXCLUDED.grade,
    section          = EXCLUDED.section,
    position_number  = EXCLUDED.position_number,
    sub_question     = EXCLUDED.sub_question,
    answer_submission= EXCLUDED.answer_submission,
    correct_answer   = EXCLUDED.correct_answer,
    points_received  = EXCLUDED.points_received,
    points_possible  = EXCLUDED.points_possible,
    user_id_ques_id  = EXCLUDED.user_id_ques_id,
    grade_id         = EXCLUDED.grade_id,
    assessment_id    = EXCLUDED.assessment_id,
    subject_id       = EXCLUDED.subject_id,
    strand_id        = EXCLUDED.strand_id,
    standard         = EXCLUDED.standard,
    identifier       = EXCLUDED.identifier;
