-- 8 cubes. Column lists ported from Schoology_py.ipynb section 7 and PBIX
-- 03_schema.csv. PK `id` is the SHA-256-hex hash described per cube.
-- school_id is added on every cube for RLS even where the notebook output
-- groups by School_ID (CSV string) — we attach our UUID-based school_id at
-- write time.

CREATE TABLE cube_grade_summary (
  id                            TEXT PRIMARY KEY,
  school_id                     UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  school_id_csv                 TEXT,
  subject_id                    TEXT,
  item_id                       TEXT,
  grade_average                 NUMERIC,
  percentage_incorrect_answers  NUMERIC,
  grade_min                     NUMERIC,
  grade_max                     NUMERIC
);
CREATE INDEX cube_grade_summary_school_idx ON cube_grade_summary (school_id);
CREATE INDEX cube_grade_summary_school_item_idx ON cube_grade_summary (school_id, item_id);
CREATE INDEX cube_grade_summary_school_subject_idx ON cube_grade_summary (school_id, subject_id);

CREATE TABLE cube_school_summary (
  id                            TEXT PRIMARY KEY,
  school_id                     UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  school_id_csv                 TEXT,
  subject_id                    TEXT,
  item_id                       TEXT,
  total_questions               BIGINT,
  total_standards               BIGINT,
  total_students                BIGINT,
  total_possible_point          NUMERIC,
  total_score                   NUMERIC,
  grade_average                 NUMERIC,
  percentage_incorrect_answers  NUMERIC
);
CREATE INDEX cube_school_summary_school_idx ON cube_school_summary (school_id);
CREATE INDEX cube_school_summary_school_item_idx ON cube_school_summary (school_id, item_id);
CREATE INDEX cube_school_summary_school_subject_idx ON cube_school_summary (school_id, subject_id);

CREATE TABLE cube_standard_summary (
  id                            TEXT PRIMARY KEY,
  school_id                     UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  item_id                       TEXT,
  strand_id                     TEXT,
  identifier                    TEXT,
  total_questions               BIGINT,
  total_standards               BIGINT,
  total_possible_point          NUMERIC,
  total_score                   NUMERIC,
  grade_average                 NUMERIC,
  percentage_incorrect_answers  NUMERIC
);
CREATE INDEX cube_standard_summary_school_idx ON cube_standard_summary (school_id);
CREATE INDEX cube_standard_summary_school_item_idx ON cube_standard_summary (school_id, item_id);
CREATE INDEX cube_standard_summary_strand_idx ON cube_standard_summary (strand_id);
CREATE INDEX cube_standard_summary_identifier_idx ON cube_standard_summary (identifier);

CREATE TABLE cube_question_summary (
  id                              TEXT PRIMARY KEY,
  school_id                       UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  school_id_csv                   TEXT,
  question_id                     TEXT,
  item_id                         TEXT,
  item_name                       TEXT,
  subject_id                      TEXT,
  position_number                 TEXT,
  question                        TEXT,
  question_no                     TEXT,
  question_no_url                 TEXT,
  question_type                   TEXT,
  associated_question_id          TEXT,
  total_points                    TEXT,
  total_possible_point            NUMERIC,
  total_score                     NUMERIC,
  grade_average                   NUMERIC,
  percentage_incorrect_answers    NUMERIC,
  least_points_earned             TEXT,
  most_points_earned              TEXT,
  average_points_earned           TEXT,
  correct_answer                  TEXT,
  correctly_answered              TEXT,
  sub_question                    TEXT,
  session                         TEXT,
  assessment_type                 TEXT,
  subject                         TEXT,
  grade                           TEXT,
  section                         TEXT,
  identifier                      TEXT,
  standard                        TEXT,
  standards                       TEXT,
  qkey                            TEXT,
  ukey                            TEXT,
  assessment_date                 TEXT,
  section_name                    TEXT,
  section_instructors             TEXT,
  item_type                       TEXT,
  incorrect_choice_details        TEXT,
  incorrect_details_name          TEXT,
  incorrect_choice_details_hash   TEXT,
  incorrect_details_name_hash     TEXT,
  teacher_name_hash               TEXT
);
CREATE INDEX cube_question_summary_school_idx ON cube_question_summary (school_id);
CREATE INDEX cube_question_summary_school_item_idx ON cube_question_summary (school_id, item_id);
CREATE INDEX cube_question_summary_school_question_idx ON cube_question_summary (school_id, question_id);
CREATE INDEX cube_question_summary_school_ukey_idx ON cube_question_summary (school_id, ukey);

CREATE TABLE cube_questionincorrectchoice_summary (
  id                            TEXT PRIMARY KEY,
  school_id                     UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  question_id                   TEXT,
  ukey                          TEXT,
  answer_submission             TEXT,
  total_student                 BIGINT,
  total_possible_point          NUMERIC,
  total_score                   NUMERIC,
  grade_average                 NUMERIC,
  percentage_incorrect_answers  NUMERIC
);
CREATE INDEX cube_qic_summary_school_idx ON cube_questionincorrectchoice_summary (school_id);
CREATE INDEX cube_qic_summary_school_question_idx ON cube_questionincorrectchoice_summary (school_id, question_id);
CREATE INDEX cube_qic_summary_ukey_idx ON cube_questionincorrectchoice_summary (ukey);

CREATE TABLE cube_question_summary_overall (
  id                              TEXT PRIMARY KEY,
  school_id                       UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  subject_id                      TEXT,
  ukey                            TEXT,
  question_no                     TEXT,
  sorting_question_no             TEXT,
  question                        TEXT,
  question_no_url                 TEXT,
  position_number                 TEXT,
  correct_answer                  TEXT,
  total_possible_point            NUMERIC,
  total_score                     NUMERIC,
  grade_average                   NUMERIC,
  percentage_incorrect_answers    NUMERIC,
  standards                       TEXT,
  description                     TEXT,
  trimmed_standard                TEXT,
  section_instructors             TEXT,
  incorrect_choice_details        TEXT,
  incorrect_details_name          TEXT,
  incorrect_choice_details_hash   TEXT,
  incorrect_details_name_hash     TEXT,
  teacher_name_hash               TEXT
);
CREATE INDEX cube_qso_school_idx ON cube_question_summary_overall (school_id);
CREATE INDEX cube_qso_subject_idx ON cube_question_summary_overall (school_id, subject_id);
CREATE INDEX cube_qso_ukey_idx ON cube_question_summary_overall (ukey);

CREATE TABLE cube_overallperformance_summary (
  id                            TEXT PRIMARY KEY,
  school_id                     UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  identifier                    TEXT,
  item_id                       TEXT,
  item_name                     TEXT,
  question_id                   TEXT,
  question_no                   TEXT,
  standards                     TEXT,
  total_possible_point          NUMERIC,
  total_score                   NUMERIC,
  grade_average                 NUMERIC,
  percentage_incorrect_answers  NUMERIC
);
CREATE INDEX cube_overallperformance_summary_school_idx ON cube_overallperformance_summary (school_id);
CREATE INDEX cube_overallperformance_summary_school_item_idx ON cube_overallperformance_summary (school_id, item_id);
CREATE INDEX cube_overallperformance_summary_school_question_idx ON cube_overallperformance_summary (school_id, question_id);

CREATE TABLE cube_user_summary (
  id                                       TEXT PRIMARY KEY,
  school_id                                UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  school_id_csv                            TEXT,
  section_nid                              TEXT,
  section_instructors                      TEXT,
  session                                  TEXT,
  grade                                    TEXT,
  subject                                  TEXT,
  assessment_type                          TEXT,
  user_uid                                 TEXT,
  user_name                                TEXT,
  item_id                                  TEXT,
  item_name                                TEXT,
  question_id                              TEXT,
  question_no                              TEXT,
  standards                                TEXT,
  total_possible_point                     NUMERIC,
  total_score                              NUMERIC,
  total_possible_point_by_question         NUMERIC,
  total_score_by_question                  NUMERIC,
  total_possible_point_by_overall          NUMERIC,
  total_score_by_overall                   NUMERIC,
  total_possible_point_by_overall_year     NUMERIC,
  total_score_by_overall_year              NUMERIC,
  total_possible_point_by_item             NUMERIC,
  total_score_by_item                      NUMERIC,
  total_possible_point_by_section          NUMERIC,
  total_score_by_section                   NUMERIC,
  total_possible_point_by_standard         NUMERIC,
  total_score_by_standard                  NUMERIC,
  count_student                            BIGINT,
  user_possible_point                      NUMERIC,
  user_overall_possible_point              NUMERIC,
  student_name_hash                        TEXT,
  teacher_name_hash                        TEXT
);
CREATE INDEX cube_user_summary_school_idx ON cube_user_summary (school_id);
CREATE INDEX cube_user_summary_school_item_idx ON cube_user_summary (school_id, item_id);
CREATE INDEX cube_user_summary_school_user_idx ON cube_user_summary (school_id, user_uid);
CREATE INDEX cube_user_summary_school_section_idx ON cube_user_summary (school_id, section_nid);

-- I3 — document `id` formula on every cube. Each `id` is the SHA-256-hex of a
-- concat per the legacy notebook §7 (Schoology_py.ipynb). The exact concat
-- columns differ per cube; see data/_pbix_extract/40_schoology_py_spec.md for
-- per-cube formulas. Phase 3 transformation must reproduce identical hashes
-- (parity tests assert this); do not change formulas without parity tests.
COMMENT ON COLUMN cube_grade_summary.id              IS 'sha256 of concat(...) per notebook §7. See 40_schoology_py_spec.md for exact formula. Phase 3 transformation must produce identical hash; do not change formula without parity tests.';
COMMENT ON COLUMN cube_school_summary.id             IS 'sha256 of concat(...) per notebook §7. See 40_schoology_py_spec.md for exact formula. Phase 3 transformation must produce identical hash; do not change formula without parity tests.';
COMMENT ON COLUMN cube_standard_summary.id           IS 'sha256 of concat(...) per notebook §7. See 40_schoology_py_spec.md for exact formula. Phase 3 transformation must produce identical hash; do not change formula without parity tests.';
COMMENT ON COLUMN cube_question_summary.id           IS 'sha256 of concat(...) per notebook §7. See 40_schoology_py_spec.md for exact formula. Phase 3 transformation must produce identical hash; do not change formula without parity tests.';
COMMENT ON COLUMN cube_questionincorrectchoice_summary.id IS 'sha256 of concat(...) per notebook §7. See 40_schoology_py_spec.md for exact formula. Phase 3 transformation must produce identical hash; do not change formula without parity tests.';
COMMENT ON COLUMN cube_question_summary_overall.id   IS 'sha256 of concat(...) per notebook §7. See 40_schoology_py_spec.md for exact formula. Phase 3 transformation must produce identical hash; do not change formula without parity tests.';
COMMENT ON COLUMN cube_overallperformance_summary.id IS 'sha256 of concat(...) per notebook §7. See 40_schoology_py_spec.md for exact formula. Phase 3 transformation must produce identical hash; do not change formula without parity tests.';
COMMENT ON COLUMN cube_user_summary.id               IS 'sha256 of concat(...) per notebook §7. See 40_schoology_py_spec.md for exact formula. Phase 3 transformation must produce identical hash; do not change formula without parity tests.';
