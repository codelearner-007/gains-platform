-- 13 dim tables (dim_standard + dim_strand are in 045_standards_seed.sql).
-- Column lists ported 1:1 from Schoology_py.ipynb section 4 (see
-- data/_pbix_extract/40_schoology_py_spec.md) and PBIX 03_schema.csv.
-- Schoology IDs (User_UID, Item_ID, Question_ID, Course_NID, Section_NID,
-- School_ID-from-CSV) are TEXT — they are not UUIDs in Schoology.
-- Synthetic SHA-256-hex keys (Subject_ID, Grade_ID, Assessment_ID,
-- session_id) are also TEXT.

-- One row per (UUID school_id). school_id_csv is the User_School_ID seen in
-- CSVs (TEXT, may differ across CSV exports). Notebook publishes this with
-- primary_key='School_ID' (line 851) — one row per school. (B4 fix.)
CREATE TABLE dim_school (
  school_id     UUID PRIMARY KEY REFERENCES schools(school_id) ON DELETE CASCADE,
  school_id_csv TEXT NOT NULL,
  school_name   TEXT NOT NULL,
  UNIQUE (school_id, school_id_csv)
);
CREATE INDEX dim_school_school_id_idx ON dim_school (school_id);

CREATE TABLE dim_student (
  uid                       TEXT NOT NULL,
  school_id                 UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  id                        TEXT,
  school_id_csv             TEXT,
  school_uid                TEXT,
  name_title                TEXT,
  name_first                TEXT,
  name_first_preferred      TEXT,
  use_preferred_first_name  BOOLEAN,
  name_middle               TEXT,
  name_middle_show          BOOLEAN,
  name_last                 TEXT,
  name_display              TEXT,
  primary_email             TEXT,
  picture_url               TEXT,
  gender                    TEXT,
  position                  TEXT,
  grad_year                 TEXT,
  username                  TEXT,
  -- password_hash from Schoology /users API. NEVER store cleartext. (B5 fix.)
  password_hash             TEXT,
  role_id                   TEXT,
  tz_offset                 TEXT,
  tz_name                   TEXT,
  language                  TEXT,
  PRIMARY KEY (school_id, uid)
);
CREATE INDEX dim_student_school_idx ON dim_student (school_id);
CREATE INDEX dim_student_uid_idx ON dim_student (uid);

CREATE TABLE dim_teacher (
  uid                       TEXT NOT NULL,
  school_id                 UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  id                        TEXT,
  school_id_csv             TEXT,
  name_title                TEXT,
  name_first                TEXT,
  name_first_preferred      TEXT,
  use_preferred_first_name  BOOLEAN,
  name_middle               TEXT,
  name_middle_show          BOOLEAN,
  name_last                 TEXT,
  name_display              TEXT,
  primary_email             TEXT,
  picture_url               TEXT,
  gender                    TEXT,
  position                  TEXT,
  grad_year                 TEXT,
  username                  TEXT,
  -- password_hash from Schoology /users API. NEVER store cleartext. (B5 fix.)
  password_hash             TEXT,
  role_id                   TEXT,
  tz_offset                 TEXT,
  tz_name                   TEXT,
  language                  TEXT,
  PRIMARY KEY (school_id, uid)
);
CREATE INDEX dim_teacher_school_idx ON dim_teacher (school_id);
CREATE INDEX dim_teacher_uid_idx ON dim_teacher (uid);

CREATE TABLE dim_parent (
  uid                       TEXT NOT NULL,
  school_id                 UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  id                        TEXT,
  school_id_csv             TEXT,
  school_uid                TEXT,
  name_title                TEXT,
  name_first                TEXT,
  name_first_preferred      TEXT,
  use_preferred_first_name  BOOLEAN,
  name_middle               TEXT,
  name_middle_show          BOOLEAN,
  name_last                 TEXT,
  name_display              TEXT,
  primary_email             TEXT,
  picture_url               TEXT,
  gender                    TEXT,
  position                  TEXT,
  grad_year                 TEXT,
  username                  TEXT,
  -- password_hash from Schoology /users API. NEVER store cleartext. (B5 fix.)
  password_hash             TEXT,
  role_id                   TEXT,
  tz_offset                 TEXT,
  tz_name                   TEXT,
  language                  TEXT,
  child_uids                TEXT[],
  PRIMARY KEY (school_id, uid)
);
CREATE INDEX dim_parent_school_idx ON dim_parent (school_id);
CREATE INDEX dim_parent_uid_idx ON dim_parent (uid);

CREATE TABLE dim_course (
  course_nid    TEXT NOT NULL,
  school_id     UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  course_name   TEXT,
  course_code   TEXT,
  school_id_csv TEXT,
  PRIMARY KEY (school_id, course_nid)
);
CREATE INDEX dim_course_school_idx ON dim_course (school_id);

CREATE TABLE dim_item (
  item_id              TEXT NOT NULL,
  school_id            UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  subject_id           TEXT,
  item_type            TEXT,
  item_name            TEXT,
  school_id_csv        TEXT,
  section_name         TEXT,
  section_instructors  TEXT,
  assessment_date      DATE,
  PRIMARY KEY (school_id, item_id)
);
CREATE INDEX dim_item_school_idx ON dim_item (school_id);
CREATE INDEX dim_item_subject_idx ON dim_item (school_id, subject_id);

CREATE TABLE dim_question_data (
  qkey                   TEXT NOT NULL,
  school_id              UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  ukey                   TEXT,
  question               TEXT,
  position_number        TEXT,
  item_id                TEXT,
  item_name              TEXT,
  school_id_csv          TEXT,
  standards              TEXT,
  question_id            TEXT,
  question_no            TEXT,
  least_points_earned    TEXT,
  correct_answer         TEXT,
  question_type          TEXT,
  average_points_earned  TEXT,
  associated_question_id TEXT,
  total_points           TEXT,
  most_points_earned     TEXT,
  correctly_answered     TEXT,
  sub_question           TEXT,
  session                TEXT,
  assessment_type        TEXT,
  subject                TEXT,
  grade                  TEXT,
  section                TEXT,
  standard               TEXT,
  identifier             TEXT,
  PRIMARY KEY (school_id, qkey)
);
CREATE INDEX dim_question_data_school_idx ON dim_question_data (school_id);
CREATE INDEX dim_question_data_school_item_idx ON dim_question_data (school_id, item_id);
CREATE INDEX dim_question_data_school_question_idx ON dim_question_data (school_id, question_id);
CREATE INDEX dim_question_data_identifier_idx ON dim_question_data (identifier);

CREATE TABLE dim_unit_lesson (
  item_id      TEXT NOT NULL,
  school_id    UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  item_name    TEXT,
  school_id_csv TEXT,
  PRIMARY KEY (school_id, item_id)
);
CREATE INDEX dim_unit_lesson_school_idx ON dim_unit_lesson (school_id);

CREATE TABLE dim_section (
  section_nid          TEXT NOT NULL,
  school_id            UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  section_code         TEXT,
  item_id              TEXT,
  section_name         TEXT,
  section_instructors  TEXT,
  school_id_csv        TEXT,
  PRIMARY KEY (school_id, section_nid)
);
CREATE INDEX dim_section_school_idx ON dim_section (school_id);
CREATE INDEX dim_section_school_item_idx ON dim_section (school_id, item_id);

CREATE TABLE dim_session (
  session_id    TEXT NOT NULL,
  school_id     UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  school_id_csv TEXT,
  session       TEXT,
  PRIMARY KEY (school_id, session_id)
);
CREATE INDEX dim_session_school_idx ON dim_session (school_id);

CREATE TABLE dim_grade (
  grade_id      TEXT NOT NULL,
  school_id     UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  school_id_csv TEXT,
  grade         TEXT,
  PRIMARY KEY (school_id, grade_id)
);
CREATE INDEX dim_grade_school_idx ON dim_grade (school_id);

CREATE TABLE dim_assessment_type (
  assessment_id   TEXT NOT NULL,
  school_id       UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  school_id_csv   TEXT,
  assessment_type TEXT,
  PRIMARY KEY (school_id, assessment_id)
);
CREATE INDEX dim_assessment_type_school_idx ON dim_assessment_type (school_id);

CREATE TABLE dim_subject (
  subject_id           TEXT NOT NULL,
  school_id            UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  school_id_csv        TEXT,
  subject              TEXT,
  assessment_type      TEXT,
  grade                TEXT,
  session              TEXT,
  item_name            TEXT,
  grade_sort           TEXT,
  show_history_subject TEXT,
  grade_no             TEXT,
  PRIMARY KEY (school_id, subject_id)
);
CREATE INDEX dim_subject_school_idx ON dim_subject (school_id);
