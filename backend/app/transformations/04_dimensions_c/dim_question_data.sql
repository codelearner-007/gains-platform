-- dim_question_data — one row per (school_id, qkey).
-- Notebook lines 945-1029 (40_schoology_py_spec.md §4.5):
--   1. Join question_data -> dim_item to resolve School_ID by Item_ID.
--   2. Drop the original `Standards` (multi-melt-key column) and rename
--      Standards_Val -> Standard.
--   3. Project the 23 columns listed in the notebook.
--   4. Grade 9-12 -> "Regular 9–12" remap (already applied at staging via
--      school_grade_overrides; nothing extra to do here).
--   5. SUBSTRING JOIN on standards: dim_question_data.standard ILIKE
--      '%' || dim_standard.schoology_standard || '%'. This intentionally
--      multi-matches on prefixes (e.g. MA.7.DP.2 inside MA.7.DP.2.1) — the
--      notebook then dropDuplicates so we DISTINCT ON (qkey) at the end.
--   6. Compute Qkey (composite text PK) and Ukey (sha256 hash) per notebook
--      lines 996-1018, with COALESCE to literal default tokens for NULLs.
--   7. publish primary_key='Qkey'.
--
-- Multi-match handling: a single (school_id, question_id, standard) row may
-- match several dim_standard.schoology_standard codes. The legacy notebook
-- emits a row per match and then dropDuplicates on the publish PK. We use
-- DISTINCT ON (school_id, qkey) ORDER BY identifier NULLS LAST so the row
-- with a non-NULL identifier wins on collision.

INSERT INTO dim_question_data (
  qkey, school_id, ukey, question, position_number, item_id, item_name,
  standards, question_id, question_no, least_points_earned,
  correct_answer, question_type, average_points_earned, associated_question_id,
  total_points, most_points_earned, correctly_answered, sub_question, session,
  assessment_type, subject, grade, section, standard, identifier
)
WITH qd_with_school AS (
  -- Join Item_ID -> dim_item to resolve school_id for question rows.
  SELECT
    qd.*,
    di.school_id AS resolved_school_id
  FROM stg_question_data qd
  LEFT JOIN dim_item di
    ON di.school_id = qd.school_id
   AND di.item_id   = qd.item_id
),
qd_filtered AS (
  -- Both school_id columns ought to agree (qd.school_id is set at staging
  -- already from raw_question_data.school_id). We keep the staging value but
  -- enforce the join is non-empty for items that exist in dim_item.
  SELECT
    school_id,
    item_id,
    item_name,
    question_id,
    question_no,
    associated_question_id,
    total_points,
    question_type,
    question,
    position_number,
    sub_question,
    correct_answer,
    correctly_answered,
    most_points_earned,
    least_points_earned,
    average_points_earned,
    standards_val,
    session,
    assessment_type,
    subject,
    grade,
    section
  FROM qd_with_school
  WHERE question_id IS NOT NULL
),
qd_with_standard AS (
  -- Exact-equality identifier match — notebook used Spark's substring
  -- contains (`Standard.contains(Schoology_Standard)`), which the original
  -- SQL port transliterated as `standards_val ILIKE '%' || schoology_standard
  -- || '%'`. That substring match collides on dotted-prefix codes: a question
  -- with `AI.MA.912.AR.1.7` matches BOTH `MA.912.AR.1.7` AND the cluster code
  -- `MA.912.AR.1` (prefix), causing DISTINCT-ON lexicographic tiebreak to
  -- stamp the WRONG identifier (Q11 in item 8359960427 was getting AR.1.3's
  -- identifier `3cc52b67...` instead of AR.1.7's `3cc92b67...`).
  --
  -- Empirical check (see audit): every distinct `standards_val` produced by
  -- staging is an exact match for at least one `schoology_standard` row in
  -- `dim_standard` (27 / 28 distinct codes in the corpus; the one non-match
  -- is the literal text `Social Studies`, which is a category label, not a
  -- standard code, and rightfully maps to no identifier). Exact equality is
  -- therefore strictly sufficient AND avoids both the prefix-collision and
  -- the POSIX-regex escape-class footguns.
  --
  -- See `.hermes/report-parity/pipeline-audit-2026-05-18.md §B1`.
  SELECT
    q.*,
    ds.identifier         AS standard_identifier,
    ds.schoology_standard AS matched_schoology_standard
  FROM qd_filtered q
  LEFT JOIN dim_standard ds
    ON ds.schoology_standard IS NOT NULL
   AND q.standards_val IS NOT NULL
   AND q.standards_val = ds.schoology_standard
),
qd_keys AS (
  SELECT
    *,
    -- Qkey: notebook lines 350-353 (40_schoology_py_spec.md §4.5):
    --   concat(session, assessment_type, subject, grade, question_id,
    --          position_number, correct_answer, standard, school_id)
    -- with COALESCE-to-literal defaults so NULLs do not collapse rows.
    CONCAT(
      COALESCE(session,         'DEFAULT_SESSION'),
      COALESCE(assessment_type, 'DEFAULT_TYPE'),
      COALESCE(subject,         'DEFAULT_SUBJECT'),
      COALESCE(grade,           'DEFAULT_GRADE'),
      COALESCE(question_id,     'DEFAULT_QID'),
      COALESCE(position_number, 'n/a'),
      COALESCE(correct_answer,  'n/a'),
      COALESCE(standards_val,   'n/a'),
      COALESCE(school_id::text, 'DEFAULT_SCHOOL')
    ) AS qkey,
    -- Ukey: notebook line 352 — generate_uuid_8(School_ID, Session,
    -- Assessment_type, Item_Name, Subject, Grade, Question, Correct_Answer)
    uuid_8(
      school_id::text,
      session,
      assessment_type,
      item_name,
      subject,
      grade,
      question,
      correct_answer
    ) AS ukey
  FROM qd_with_standard
),
deduped AS (
  -- Word-boundary join can still yield >1 rows per (school_id, qkey) when a
  -- dim_standard identifier has multiple equivalent schoology codes (e.g.
  -- `MA.912.AR.1.7` and `AI.MA.912.AR.1.7` both belong to identifier
  -- `3cc92b67…`). All such rows resolve to the same identifier — the dedupe
  -- below picks the row whose `schoology_standard` matched longest, which
  -- guarantees the most specific code wins if the schema ever ships two
  -- identifiers whose codes are mutual prefixes despite the word-boundary
  -- guard. See `.hermes/report-parity/pipeline-audit-2026-05-18.md §B1`.
  SELECT DISTINCT ON (school_id, qkey)
    qkey, school_id, ukey, question, position_number, item_id, item_name,
    standards_val,
    question_id, question_no, least_points_earned, correct_answer,
    question_type, average_points_earned, associated_question_id,
    total_points, most_points_earned, correctly_answered, sub_question,
    session, assessment_type, subject, grade, section,
    standards_val AS standard,
    standard_identifier AS identifier
  FROM qd_keys
  ORDER BY
    school_id,
    qkey,
    standard_identifier NULLS LAST,
    COALESCE(length(matched_schoology_standard), 0) DESC,
    matched_schoology_standard
)
SELECT
  qkey, school_id, ukey, question, position_number, item_id, item_name,
  standards_val             AS standards,
  question_id, question_no,
  least_points_earned::TEXT AS least_points_earned,
  correct_answer, question_type,
  average_points_earned::TEXT AS average_points_earned,
  associated_question_id,
  total_points::TEXT        AS total_points,
  most_points_earned::TEXT  AS most_points_earned,
  correctly_answered::TEXT  AS correctly_answered,
  sub_question, session, assessment_type, subject, grade, section,
  standard, identifier
FROM deduped
-- Conflict target is the (school_id, md5(qkey)) UNIQUE index (migration
-- 20260611000100): qkey can exceed the btree limit when correct_answer embeds a
-- base64 image, so the dedup index is on its hash. Semantics are unchanged.
ON CONFLICT (school_id, md5(qkey)) DO UPDATE
SET ukey                   = EXCLUDED.ukey,
    question               = EXCLUDED.question,
    position_number        = EXCLUDED.position_number,
    item_id                = EXCLUDED.item_id,
    item_name              = EXCLUDED.item_name,
    standards              = EXCLUDED.standards,
    question_id            = EXCLUDED.question_id,
    question_no            = EXCLUDED.question_no,
    least_points_earned    = EXCLUDED.least_points_earned,
    correct_answer         = EXCLUDED.correct_answer,
    question_type          = EXCLUDED.question_type,
    average_points_earned  = EXCLUDED.average_points_earned,
    associated_question_id = EXCLUDED.associated_question_id,
    total_points           = EXCLUDED.total_points,
    most_points_earned     = EXCLUDED.most_points_earned,
    correctly_answered     = EXCLUDED.correctly_answered,
    sub_question           = EXCLUDED.sub_question,
    session                = EXCLUDED.session,
    assessment_type        = EXCLUDED.assessment_type,
    subject                = EXCLUDED.subject,
    grade                  = EXCLUDED.grade,
    section                = EXCLUDED.section,
    standard               = EXCLUDED.standard,
    identifier             = EXCLUDED.identifier;
