-- cube_question_summary_overall — per-(subject_id, question, position, correct
-- answer, standard) latest-attempt rollup with incorrect-choice analysis.
-- Notebook lines 1953-2189 (40_schoology_py_spec.md §7).
--
-- Pipeline:
--   1. Latest-attempt window: row_number per
--      (Section_NID, Session, Grade, Subject, Assessment_type, School_ID,
--       User_UID, Item_ID, Question_ID)
--      ORDER BY Submission DESC, Total_Seconds DESC.
--      total_seconds = epoch(total_time).
--   2. Group by (uKey, Subject_ID, Question_No, Question, Position_Number,
--               Correct_Answer, Standard) for totals/grade_average.
--   3. Incorrect-choice analysis: same shape as cube_question_summary.
--   4. Joins:
--      a. dim_subject by (school_id, subject_id) for any per-subject metadata.
--      b. dim_question_data by (question_id, item_id, item_name, position_number)
--         for question_no, qkey, ukey.
--      c. dim_standard substring match for description (line 2153).
--      d. dim_item -> section_instructors -> dim_section_hash for teacher_name_hash.
--   5. ID hash uses ukey (D1 fix per user — notebook bug at line 2173 used
--      Standards twice; we use ukey as intended).

TRUNCATE TABLE cube_question_summary_overall;

INSERT INTO cube_question_summary_overall (
  id, school_id, subject_id, ukey, question_no, sorting_question_no,
  question, question_no_url, position_number, correct_answer,
  total_possible_point, total_score, grade_average, percentage_incorrect_answers,
  standards, description, trimmed_standard, section_instructors,
  incorrect_choice_details, incorrect_details_name,
  incorrect_choice_details_hash, incorrect_details_name_hash,
  teacher_name_hash
)
WITH ranked AS (
  -- Latest-attempt filter (notebook line 2245). The ORDER BY tiebreaks on
  -- user_id_ques_id_stand (the synthetic PK) so the result is deterministic
  -- under re-run. Without this tiebreak Postgres can return different rows
  -- per run for ties on submission/total_time.
  SELECT
    f.*,
    EXTRACT(EPOCH FROM f.total_time)::bigint AS total_seconds,
    ROW_NUMBER() OVER (
      PARTITION BY f.section_nid, f.session, f.grade, f.subject,
                   f.assessment_type, f.school_id, f.user_uid, f.item_id,
                   f.question_id
      ORDER BY f.submission DESC NULLS LAST,
               EXTRACT(EPOCH FROM f.total_time) DESC NULLS LAST,
               f.user_id_ques_id_stand
    ) AS rn
  FROM fact_student_submission f
),
latest AS (
  SELECT * FROM ranked WHERE rn = 1
),
latest_with_hash AS (
  -- Bring student name hash + dim_question_data ukey/question_no onto each row.
  SELECT
    l.school_id,
    l.user_uid,
    l.user_name,
    l.section_nid,
    l.section,
    l.subject_id,
    l.item_id,
    l.item_name,
    l.question_id,
    l.position_number,
    COALESCE(l.correct_answer, 'n/a')             AS correct_answer,
    l.points_possible,
    l.points_received,
    l.standard,
    l.identifier,
    qd.question,
    qd.question_no,
    qd.qkey,
    qd.ukey,
    qd.standards,
    sh.student_name_hash,
    l.answer_submission
  FROM latest l
  LEFT JOIN (
    SELECT DISTINCT ON (school_id, question_id, position_number)
      school_id, question_id, position_number, item_id, item_name,
      question, question_no, qkey, ukey, standards
    FROM dim_question_data
    WHERE question_id IS NOT NULL
    ORDER BY school_id, question_id, position_number, ukey NULLS LAST
  ) qd
    ON qd.school_id   = l.school_id
   AND qd.question_id = l.question_id
   AND COALESCE(qd.position_number, '__NULL__')
       = COALESCE(l.position_number, '__NULL__')
  LEFT JOIN dim_student_hash sh
    ON sh.school_id = l.school_id
   AND sh.user_uid  = l.user_uid
),
totals AS (
  -- Per-output-grain totals (notebook 1996-2010).
  SELECT
    school_id,
    subject_id,
    ukey,
    question_no,
    question,
    position_number,
    correct_answer,
    standard,
    SUM(points_possible)        AS total_possible_point,
    SUM(points_received)        AS total_score,
    SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                                AS grade_average,
    1 - SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                                AS percentage_incorrect_answers
  FROM latest_with_hash
  GROUP BY school_id, subject_id, ukey, question_no, question,
           position_number, correct_answer, standard
),
total_submissions AS (
  -- Total attempts per output grain (denominator for choice %).
  SELECT
    school_id, subject_id, ukey, question_no, question, position_number,
    correct_answer, standard,
    COUNT(*) AS total_count
  FROM latest_with_hash
  GROUP BY school_id, subject_id, ukey, question_no, question,
           position_number, correct_answer, standard
),
choice_counts AS (
  SELECT
    f.school_id, f.subject_id, f.ukey, f.question_no, f.question,
    f.position_number, f.correct_answer, f.standard,
    f.answer_submission,
    COUNT(*)                                                          AS incorrect_count,
    string_agg(DISTINCT f.user_name, ', '         ORDER BY f.user_name)         AS chooser_names,
    string_agg(DISTINCT f.student_name_hash, ', ' ORDER BY f.student_name_hash) AS chooser_hashes
  FROM latest_with_hash f
  WHERE f.points_received IS NOT NULL
    AND f.points_possible IS NOT NULL
    AND f.points_received < f.points_possible
    AND f.answer_submission IS NOT NULL
  GROUP BY f.school_id, f.subject_id, f.ukey, f.question_no, f.question,
           f.position_number, f.correct_answer, f.standard,
           f.answer_submission
),
choice_pct AS (
  SELECT
    cc.*,
    ts.total_count,
    cc.incorrect_count::numeric / NULLIF(ts.total_count, 0) AS choice_pct
  FROM choice_counts cc
  LEFT JOIN total_submissions ts
    USING (school_id, subject_id, ukey, question_no, question,
           position_number, correct_answer, standard)
),
choice_lines AS (
  SELECT
    school_id, subject_id, ukey, question_no, question, position_number,
    correct_answer, standard, answer_submission,
    ROUND(choice_pct * 100, 1)::text || '% chose [' || answer_submission || ']'
                                                                  AS line_pct,
    '[' || answer_submission || ']:' || E'\n(' || COALESCE(chooser_names, '')  || ')'
                                                                  AS line_with_name,
    '[' || answer_submission || ']:' || E'\n(' || COALESCE(chooser_hashes, '') || ')'
                                                                  AS line_with_hash
  FROM choice_pct
),
choices_per_grain AS (
  SELECT
    school_id, subject_id, ukey, question_no, question, position_number,
    correct_answer, standard,
    LEFT(string_agg(line_pct,       ', '       ORDER BY answer_submission), 7500) AS incorrect_choice_details,
    LEFT(string_agg(line_with_name, E'\n\n'   ORDER BY answer_submission), 7500) AS incorrect_details_name,
    LEFT(string_agg(line_pct,       ', '       ORDER BY answer_submission), 7500) AS incorrect_choice_details_hash,
    LEFT(string_agg(line_with_hash, E'\n\n'   ORDER BY answer_submission), 7500) AS incorrect_details_name_hash
  FROM choice_lines
  GROUP BY school_id, subject_id, ukey, question_no, question, position_number,
           correct_answer, standard
),
desc_per_standard AS (
  -- dim_standard substring match for description (notebook line 2153).
  -- Pick one (the lexically smallest schoology_standard) deterministically.
  SELECT DISTINCT ON (long_standard)
    long_standard,
    description,
    -- Trimmed_Standard: drop the first two dot-segments (notebook line 1085).
    -- e.g. "SCI.5.SC.5.P.13.1" -> "SC.5.P.13.1".
    array_to_string(
      (string_to_array(schoology_standard, '.'))[3:],
      '.'
    ) AS trimmed_standard
  FROM (
    SELECT t.long_standard, ds.schoology_standard, ds.description
    FROM (SELECT DISTINCT standard AS long_standard FROM latest_with_hash WHERE standard IS NOT NULL) t
    JOIN dim_standard ds
      ON ds.schoology_standard IS NOT NULL
     AND t.long_standard ILIKE '%' || ds.schoology_standard || '%'
  ) sub
  ORDER BY long_standard, schoology_standard
),
section_per_item AS (
  SELECT school_id, item_id, MIN(section_nid) AS section_nid
  FROM dim_section
  WHERE section_nid IS NOT NULL
  GROUP BY school_id, item_id
),
final_rows AS (
  SELECT DISTINCT
    t.school_id,
    t.subject_id,
    t.ukey,
    t.question_no,
    t.question,
    t.position_number,
    t.correct_answer,
    t.standard,
    -- Track an item_id per output grain so we can fetch section_instructors
    -- + teacher_name_hash. The notebook joins via dim_item by Subject_ID,
    -- which would explode rows; pick a single item via MAX over the cohort.
    (SELECT MAX(l.item_id) FROM latest_with_hash l
       WHERE l.school_id = t.school_id AND l.subject_id = t.subject_id
         AND l.ukey IS NOT DISTINCT FROM t.ukey
         AND l.question_no IS NOT DISTINCT FROM t.question_no
         AND l.question    IS NOT DISTINCT FROM t.question
         AND l.position_number IS NOT DISTINCT FROM t.position_number
         AND l.correct_answer  IS NOT DISTINCT FROM t.correct_answer
         AND l.standard        IS NOT DISTINCT FROM t.standard) AS rep_item_id
  FROM totals t
)
SELECT
  encode(digest(
    -- D1 fix: notebook bug at line 2173 used Standards twice when uKey is
    -- non-null. We use ukey as the spec intends.
    CONCAT_WS(', ',
      COALESCE(t.subject_id,      'DEFAULT_SUBJECT_ID'),
      COALESCE(t.question_no,     'DEFAULT_QUESTION_NO'),
      COALESCE(t.position_number, 'DEFAULT_POSITION'),
      COALESCE(t.correct_answer,  'DEFAULT_CORRECT_ANSWER'),
      COALESCE(
        CASE WHEN t.standard IS NULL OR t.standard IN ('','null') THEN 'Other'
             ELSE t.standard END,
        'DEFAULT_STANDARDS'),
      COALESCE(t.ukey, 'DEFAULT_UKEY')
    ),
    'sha256'
  ), 'hex')                                                          AS id,
  t.school_id,
  t.subject_id,
  t.ukey,
  t.question_no,
  -- Sorting Question_No (cast/keep as text for now — notebook stores object).
  t.question_no                                                      AS sorting_question_no,
  t.question,
  TRIM(REGEXP_REPLACE(COALESCE(t.question, ''), E'<[^>]*>', '', 'g'))
                                                                     AS question_no_url,
  t.position_number,
  t.correct_answer,
  t.total_possible_point,
  t.total_score,
  t.grade_average,
  t.percentage_incorrect_answers,
  CASE
    WHEN t.standard IS NULL OR t.standard IN ('', 'null') THEN 'Other'
    ELSE t.standard
  END                                                                AS standards,
  dps.description,
  dps.trimmed_standard,
  di.section_instructors,
  cpg.incorrect_choice_details,
  cpg.incorrect_details_name,
  cpg.incorrect_choice_details_hash,
  cpg.incorrect_details_name_hash,
  dsh.teacher_name_hash
FROM totals t
LEFT JOIN final_rows fr
  ON fr.school_id            = t.school_id
 AND fr.subject_id           = t.subject_id
 AND fr.ukey IS NOT DISTINCT FROM t.ukey
 AND fr.question_no    IS NOT DISTINCT FROM t.question_no
 AND fr.question       IS NOT DISTINCT FROM t.question
 AND fr.position_number IS NOT DISTINCT FROM t.position_number
 AND fr.correct_answer IS NOT DISTINCT FROM t.correct_answer
 AND fr.standard       IS NOT DISTINCT FROM t.standard
LEFT JOIN dim_item di
  ON di.school_id = t.school_id
 AND di.item_id   = fr.rep_item_id
LEFT JOIN section_per_item spi
  ON spi.school_id = t.school_id
 AND spi.item_id   = fr.rep_item_id
LEFT JOIN dim_section_hash dsh
  ON dsh.school_id   = t.school_id
 AND dsh.section_nid = spi.section_nid
LEFT JOIN choices_per_grain cpg
  ON cpg.school_id      = t.school_id
 AND cpg.subject_id     = t.subject_id
 AND cpg.ukey           IS NOT DISTINCT FROM t.ukey
 AND cpg.question_no    IS NOT DISTINCT FROM t.question_no
 AND cpg.question       IS NOT DISTINCT FROM t.question
 AND cpg.position_number IS NOT DISTINCT FROM t.position_number
 AND cpg.correct_answer IS NOT DISTINCT FROM t.correct_answer
 AND cpg.standard       IS NOT DISTINCT FROM t.standard
LEFT JOIN desc_per_standard dps
  ON dps.long_standard = t.standard
WHERE t.school_id IS NOT NULL;
