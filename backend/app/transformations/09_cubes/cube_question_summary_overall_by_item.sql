-- cube_question_summary_overall_by_item — the per-QUESTION-CONTENT grade rollup,
-- IDENTICAL to cube_question_summary_overall's `totals` computation but grained
-- by item_id as well, so per-item reports can read a section-scoped grade.
--
-- WHY: cube_question_summary_overall is grained by (school_id, subject_id, ukey,
-- question_no, question, position_number, correct_answer, standard) and
-- subject_id = uuid_6(..., item_name) — so every SECTION of one assessment
-- (same item_name, different item_id) shares the subject_id and gets POOLED into
-- one row. The per-assessment Strand/Standard "% Correct" rollups read cqso by
-- subject_id and therefore showed a cross-section average (a teacher's report
-- mixing other sections' students). cube_question_summary lacks the latest-
-- attempt + multi-select MAX-collapse + per-(question-content) grain that cqso's
-- grade_average uses, so it cannot reproduce cqso exactly; this table replays
-- cqso's EXACT chain with item_id added.
--
-- INVARIANT (proven before use): aggregating this table back over item_id
-- (GROUP BY school_id, subject_id, ukey, ... ; SUM/SUM) reproduces
-- cube_question_summary_overall's grade_average row-for-row. So a single-section
-- assessment (subject_id → one item) is byte-identical to cqso (no baseline
-- move); a multi-section assessment is correctly split per section.

-- Table + indexes are created by
-- supabase/migrations/20260616000000_cube_question_summary_overall_by_item.sql
-- (so it exists at deploy time, before this transform runs). This file only
-- (re)populates it.
--
-- The whole populate is wrapped in a to_regclass(...) IS NOT NULL guard because
-- this twin cube is intentionally ABSENT on prod — where the table does not
-- exist the block is a no-op instead of erroring on the missing relation.
-- When present: a scoped run (temp table _scope_assessments non-empty) deletes
-- only the touched subject_ids and re-inserts them from the preserved fact. The
-- table has NO PK, so this is a plain DELETE + INSERT (never an upsert). Empty
-- scope (full rebuild) falls through to TRUNCATE — byte-identical to legacy.
DO $twin$ BEGIN
  IF to_regclass('public.cube_question_summary_overall_by_item') IS NOT NULL THEN
    IF EXISTS (SELECT 1 FROM _scope_assessments) THEN
      DELETE FROM cube_question_summary_overall_by_item
      WHERE subject_id IN (SELECT subject_id FROM _scope_assessments);
    ELSE
      TRUNCATE TABLE cube_question_summary_overall_by_item;
    END IF;

    INSERT INTO cube_question_summary_overall_by_item (
      school_id, subject_id, item_id, ukey, question_no, position_number,
      correct_answer, standards, total_possible_point, total_score, grade_average
    )
    WITH ranked AS (
  -- Latest-attempt filter — IDENTICAL to cube_question_summary_overall.sql.
  SELECT
    f.*,
    ROW_NUMBER() OVER (
      PARTITION BY f.section_nid, f.session, f.grade, f.subject,
                   f.assessment_type, f.school_id, f.user_uid, f.item_id,
                   f.question_id
      ORDER BY f.submission DESC NULLS LAST,
               EXTRACT(EPOCH FROM f.total_time) DESC NULLS LAST,
               f.user_id_ques_id_stand
    ) AS rn
  FROM fact_student_submission f
  -- Scoped rebuild: restrict the fact scan to the touched subject_ids. The
  -- latest-attempt PARTITION BY is keyed within a single subject_id, so a
  -- subject-level filter keeps or drops whole partitions and never changes the
  -- rn=1 winner. No-op when _scope_assessments is empty (full rebuild).
  WHERE (NOT EXISTS (SELECT 1 FROM _scope_assessments)
         OR f.subject_id IN (SELECT subject_id FROM _scope_assessments))
),
latest AS (
  SELECT * FROM ranked WHERE rn = 1
),
latest_with_hash AS (
  SELECT
    l.school_id,
    l.user_uid,
    l.subject_id,
    l.item_id,
    l.position_number,
    COALESCE(l.correct_answer, 'n/a') AS correct_answer,
    l.points_possible,
    l.points_received,
    l.standard,
    qd.question,
    qd.question_no,
    qd.ukey
  FROM latest l
  LEFT JOIN (
    SELECT DISTINCT ON (school_id, question_id, position_number)
      school_id, question_id, position_number, ukey, question_no, question
    FROM dim_question_data
    WHERE question_id IS NOT NULL
    ORDER BY school_id, question_id, position_number, ukey NULLS LAST
  ) qd
    ON qd.school_id   = l.school_id
   AND qd.question_id = l.question_id
   AND COALESCE(qd.position_number, '__NULL__')
       = COALESCE(l.position_number, '__NULL__')
)
-- totals — IDENTICAL to cqso's `totals` CTE, with item_id added to BOTH the
-- per-student collapse and the output grain.
SELECT
  school_id,
  subject_id,
  item_id,
  ukey,
  question_no,
  position_number,
  correct_answer,
  CASE WHEN standard IS NULL OR standard IN ('', 'null') THEN 'Other'
       ELSE standard END                                     AS standards,
  SUM(points_possible)                                       AS total_possible_point,
  SUM(points_received)                                       AS total_score,
  SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0) AS grade_average
FROM (
  SELECT
    school_id, subject_id, item_id, ukey, question_no, question,
    position_number, correct_answer, standard, user_uid,
    MAX(points_received) AS points_received,
    MAX(points_possible) AS points_possible
  FROM latest_with_hash
  GROUP BY school_id, subject_id, item_id, ukey, question_no, question,
           position_number, correct_answer, standard, user_uid
) per_student
WHERE school_id IS NOT NULL
GROUP BY school_id, subject_id, item_id, ukey, question_no, question,
         position_number, correct_answer, standard;
  END IF;
END $twin$;
