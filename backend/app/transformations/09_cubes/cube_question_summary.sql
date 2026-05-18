-- cube_question_summary — per-(item, question, position, standard, correct
-- answer) totals plus an incorrect-choice analysis string.
-- Notebook lines 1581-1771 (40_schoology_py_spec.md §7).
--
-- Pipeline:
--   1. totals: GROUP BY (item_id, question_id) -> Total_Possible_Point, Total_Score,
--      Grade_Average, Percentage_InCorrect_Answers.
--   2. incorrect-choice analysis (lines 1593-1689):
--      a. Per (question_id, position_number) count student attempts.
--      b. Per (question_id, position_number, answer_submission) count attempts
--         where points_received < points_possible (incorrect attempts).
--      c. Choice_Percentage = incorrect_count / total_count.
--      d. For each incorrect answer string, build:
--         incorrect_choice_details:      "p%% chose [answer]" (single most-chosen)
--         incorrect_details_name:        "[answer]:\n(name1, name2)"
--         incorrect_choice_details_hash: same as above with hashed names
--         incorrect_details_name_hash:   same as above with hashed names
--         All four collapsed via concat_ws across all incorrect choices in
--         that (question_id, position_number).
--   3. Attach question metadata from dim_question_data and dim_item.
--   4. Attach teacher_name_hash from dim_section_hash via section_nid.
--   5. id = sha256(school_id || item_id || item_name || question_id ||
--                  position_number || standard || correct_answer)

TRUNCATE TABLE cube_question_summary;

INSERT INTO cube_question_summary (
  id, school_id, school_id_csv, question_id, item_id, item_name, subject_id,
  position_number, question, question_no, question_no_url, question_type,
  associated_question_id, total_points,
  total_possible_point, total_score, grade_average, percentage_incorrect_answers,
  least_points_earned, most_points_earned, average_points_earned,
  correct_answer, correctly_answered, sub_question, session, assessment_type,
  subject, grade, section, identifier, standard, standards, qkey, ukey,
  assessment_date, section_name, section_instructors, item_type,
  incorrect_choice_details, incorrect_details_name,
  incorrect_choice_details_hash, incorrect_details_name_hash,
  teacher_name_hash
)
WITH fact_with_hash AS (
  -- Bring student_name_hash and section_nid onto each fact row so the
  -- incorrect-choice analysis can build both name + hash variants and the
  -- final SELECT can attach teacher_name_hash.
  SELECT
    f.school_id,
    f.school_id_csv,
    f.user_uid,
    f.user_name,
    f.section_nid,
    f.item_id,
    f.item_name,
    f.question_id,
    f.position_number,
    f.answer_submission,
    f.correct_answer,
    f.points_possible,
    f.points_received,
    f.standard,
    f.identifier,
    f.subject,
    f.subject_id,
    f.grade,
    f.session,
    f.assessment_type,
    f.section,
    sh.student_name_hash
  FROM fact_student_submission f
  LEFT JOIN dim_student_hash sh
    ON sh.school_id = f.school_id
   AND sh.user_uid  = f.user_uid
),
totals AS (
  -- Per-question totals (notebook 1583-1591).
  -- school_id is included so multi-tenant facts do not blend.
  SELECT
    school_id,
    item_id,
    question_id,
    SUM(points_possible) AS total_possible_point,
    SUM(points_received) AS total_score,
    SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                         AS grade_average,
    1 - SUM(points_received)::numeric / NULLIF(SUM(points_possible), 0)
                         AS percentage_incorrect_answers
  FROM fact_student_submission
  GROUP BY school_id, item_id, question_id
),
total_submissions AS (
  -- Total attempts per (school, question, position) — denominator for choice %.
  SELECT
    school_id,
    question_id,
    position_number,
    COUNT(*) AS total_count
  FROM fact_with_hash
  GROUP BY school_id, question_id, position_number
),
choice_counts AS (
  -- Count of INCORRECT attempts per (school, question, position,
  -- answer_submission). Only rows where points_received < points_possible
  -- count toward the incorrect-choice analysis.
  SELECT
    f.school_id,
    f.question_id,
    f.position_number,
    f.answer_submission,
    COUNT(*) AS incorrect_count,
    -- Names + hashes choosing this answer (deduped to avoid the same
    -- student appearing twice if they submitted twice).
    string_agg(DISTINCT f.user_name,         ', ' ORDER BY f.user_name)
      AS chooser_names,
    string_agg(DISTINCT f.student_name_hash, ', ' ORDER BY f.student_name_hash)
      AS chooser_hashes
  FROM fact_with_hash f
  WHERE f.points_received IS NOT NULL
    AND f.points_possible IS NOT NULL
    AND f.points_received < f.points_possible
    AND f.answer_submission IS NOT NULL
  GROUP BY f.school_id, f.question_id, f.position_number, f.answer_submission
),
choice_pct AS (
  SELECT
    cc.school_id,
    cc.question_id,
    cc.position_number,
    cc.answer_submission,
    cc.incorrect_count,
    cc.chooser_names,
    cc.chooser_hashes,
    ts.total_count,
    cc.incorrect_count::numeric / NULLIF(ts.total_count, 0) AS choice_pct
  FROM choice_counts cc
  LEFT JOIN total_submissions ts
    USING (school_id, question_id, position_number)
),
choice_lines AS (
  -- One line per incorrect (school, question, position, answer):
  --   line_pct      = "<pct>% chose [<answer>]"
  --   line_with_name= "[<answer>]:\n(<comma-separated names>)"
  --   line_with_hash= "[<answer>]:\n(<comma-separated hashes>)"
  SELECT
    school_id,
    question_id,
    position_number,
    answer_submission,
    ROUND(choice_pct * 100, 1)::text || '% chose [' || answer_submission || ']'
                                                            AS line_pct,
    '[' || answer_submission || ']:' || E'\n(' || COALESCE(chooser_names, '')  || ')'
                                                            AS line_with_name,
    '[' || answer_submission || ']:' || E'\n(' || COALESCE(chooser_hashes, '') || ')'
                                                            AS line_with_hash
  FROM choice_pct
),
choices_per_question AS (
  -- Aggregate the per-line strings to one row per (school, question, position).
  -- Truncate to 7500 chars per the notebook (line 1672).
  SELECT
    school_id,
    question_id,
    position_number,
    LEFT(string_agg(line_pct,       ', '       ORDER BY answer_submission), 7500)
                                              AS incorrect_choice_details,
    LEFT(string_agg(line_with_name, E'\n\n'   ORDER BY answer_submission), 7500)
                                              AS incorrect_details_name,
    LEFT(string_agg(line_pct,       ', '       ORDER BY answer_submission), 7500)
                                              AS incorrect_choice_details_hash,
    LEFT(string_agg(line_with_hash, E'\n\n'   ORDER BY answer_submission), 7500)
                                              AS incorrect_details_name_hash
  FROM choice_lines
  GROUP BY school_id, question_id, position_number
),
qd AS (
  -- DISTINCT ON (school_id, question_id, position_number, identifier) — one
  -- row per (question, identifier) so multi-standard questions retain ALL
  -- their (standard, identifier) pairs instead of collapsing to the
  -- lexicographically smallest identifier. See
  -- `.hermes/report-parity/pipeline-audit-2026-05-18.md §B2`.
  SELECT DISTINCT ON (school_id, question_id, position_number, identifier)
    school_id, question_id, position_number,
    item_id, item_name, question, question_no, question_type,
    associated_question_id, total_points, least_points_earned,
    most_points_earned, average_points_earned, correct_answer,
    correctly_answered, sub_question, session, assessment_type,
    subject, grade, section, standard, identifier, standards, qkey, ukey
  FROM dim_question_data
  WHERE question_id IS NOT NULL
  ORDER BY school_id, question_id, position_number, identifier NULLS LAST
),
di AS (
  -- dim_item by (school_id, item_id) -> assessment_date, section_name,
  -- section_instructors, item_type. PK is already (school_id, item_id) so no
  -- DISTINCT ON needed.
  SELECT
    school_id, item_id, subject_id, item_type, item_name, school_id_csv,
    section_name, section_instructors, assessment_date
  FROM dim_item
),
ds AS (
  -- For section_nid -> teacher_name_hash. dim_section_hash PK is
  -- (school_id, section_nid).
  SELECT school_id, section_nid, teacher_name_hash
  FROM dim_section_hash
),
section_per_item AS (
  -- One representative section_nid per (school_id, item_id) so we can join
  -- the teacher name hash on this cube without exploding rows. dim_section
  -- PK is (school_id, section_nid) and there can be many sections per item.
  -- We pick MIN(section_nid) for determinism.
  SELECT school_id, item_id, MIN(section_nid) AS section_nid
  FROM dim_section
  WHERE section_nid IS NOT NULL
  GROUP BY school_id, item_id
)
SELECT
  -- Digest extends the legacy 7-part PK with `identifier` because the grain
  -- now emits one row per (question, identifier) — multiple identifiers can
  -- share the same `standard` text (e.g. duplicate dim_standard rows where
  -- the same schoology_standard appears under two different identifiers).
  -- See `.hermes/report-parity/pipeline-audit-2026-05-18.md §B2`.
  encode(digest(
    COALESCE(f_meta.school_id::text,'DEFAULT_SCHOOL_ID')      ||
    COALESCE(f_meta.item_id,        'DEFAULT_ITEM_ID')        ||
    COALESCE(di.item_name,          'DEFAULT_ITEM_NAME')      ||
    COALESCE(f_meta.question_id,    'DEFAULT_QUESTION_ID')    ||
    COALESCE(f_meta.position_number,'DEFAULT_POSITION')       ||
    COALESCE(qd.standard,           'DEFAULT_STANDARD')       ||
    COALESCE(qd.correct_answer,     'DEFAULT_CORRECT_ANSWER') ||
    COALESCE(f_meta.identifier,     'DEFAULT_IDENTIFIER'),
    'sha256'
  ), 'hex')                                                    AS id,
  f_meta.school_id,
  f_meta.school_id_csv,
  f_meta.question_id,
  f_meta.item_id,
  COALESCE(di.item_name, f_meta.item_name)                     AS item_name,
  f_meta.subject_id,
  f_meta.position_number,
  qd.question,
  qd.question_no,
  -- question_no_url: HTML-stripped Question text (notebook 1727).
  TRIM(REGEXP_REPLACE(COALESCE(qd.question, ''), E'<[^>]*>', '', 'g'))
                                                               AS question_no_url,
  qd.question_type,
  qd.associated_question_id,
  qd.total_points,
  totals.total_possible_point,
  totals.total_score,
  totals.grade_average,
  totals.percentage_incorrect_answers,
  qd.least_points_earned,
  qd.most_points_earned,
  qd.average_points_earned,
  qd.correct_answer,
  qd.correctly_answered,
  qd.sub_question,
  qd.session,
  qd.assessment_type,
  qd.subject,
  qd.grade,
  qd.section,
  COALESCE(f_meta.identifier, 'Other')                         AS identifier,
  qd.standard,
  -- Standards: NULL/'null' -> 'Other' (notebook §8).
  CASE
    WHEN qd.standards IS NULL OR qd.standards IN ('', 'null') THEN 'Other'
    ELSE qd.standards
  END                                                          AS standards,
  qd.qkey,
  qd.ukey,
  -- assessment_date is DATE in dim_item; cube schema is TEXT (notebook stores
  -- the MM/dd/yyyy string). Format consistently.
  to_char(di.assessment_date, 'MM/DD/YYYY')                    AS assessment_date,
  di.section_name,
  di.section_instructors,
  di.item_type,
  cpq.incorrect_choice_details,
  cpq.incorrect_details_name,
  cpq.incorrect_choice_details_hash,
  cpq.incorrect_details_name_hash,
  ds.teacher_name_hash
FROM (
  -- Per-output-grain key. The previous grain was
  -- (school_id, item_id, question_id, position_number) which dropped every
  -- identifier but one per question. We add `identifier` to the grain so
  -- each (question, identifier) pair emits a row — restoring the 11
  -- distinct identifiers per item that fact and dim_standard_summary
  -- already carry. The cube_question_summary.id digest already includes
  -- `standard`, so rows still have unique primary keys.
  -- See `.hermes/report-parity/pipeline-audit-2026-05-18.md §B2`.
  SELECT DISTINCT ON (school_id, item_id, question_id, position_number, identifier)
    school_id, school_id_csv, item_id, item_name, question_id,
    position_number, subject_id, identifier
  FROM fact_student_submission
  ORDER BY school_id, item_id, question_id, position_number, identifier NULLS LAST
) f_meta
LEFT JOIN totals
  ON totals.school_id   = f_meta.school_id
 AND totals.item_id     = f_meta.item_id
 AND totals.question_id = f_meta.question_id
-- The (question_id, position_number) pair uniquely identifies a question's
-- presentational metadata (question text, question_no, correct_answer, etc.);
-- those are invariant across standards alignment. dim_question_data is
-- deduplicated by qkey (which includes standards_val), so a single source
-- question can have multiple qd rows with different identifiers. We pick
-- one deterministically rather than constraining the JOIN on
-- f_meta.identifier — that would leave the alternate-identifier rows
-- introduced by the grain change with NULL question text.
LEFT JOIN LATERAL (
  SELECT q.*
  FROM qd q
  WHERE q.school_id   = f_meta.school_id
    AND q.question_id = f_meta.question_id
    AND COALESCE(q.position_number, '__NULL__')
        = COALESCE(f_meta.position_number, '__NULL__')
  ORDER BY q.identifier NULLS LAST
  LIMIT 1
) qd ON TRUE
LEFT JOIN di
  ON di.school_id       = f_meta.school_id
 AND di.item_id         = f_meta.item_id
LEFT JOIN choices_per_question cpq
  ON cpq.school_id      = f_meta.school_id
 AND cpq.question_id    = f_meta.question_id
 AND COALESCE(cpq.position_number, '__NULL__')
     = COALESCE(f_meta.position_number, '__NULL__')
LEFT JOIN section_per_item spi
  ON spi.school_id      = f_meta.school_id
 AND spi.item_id        = f_meta.item_id
LEFT JOIN ds
  ON ds.school_id       = f_meta.school_id
 AND ds.section_nid     = spi.section_nid;
