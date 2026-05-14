-- fact_student_submission — 35-column grain row per
-- (User_UID, Question_ID, Position_Number, Answer_Submission, Submission, Standard).
-- Column list ported 1:1 from Schoology_py.ipynb section 5 (lines 1224, 1255-1268)
-- and PBIX 03_schema.csv lines 188-222.
-- PK is the 8-part coalesce-concat synthetic key built at notebook line 1270.

CREATE TABLE fact_student_submission (
  user_id_ques_id_stand   TEXT PRIMARY KEY,
  school_id               UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  user_uid                TEXT,
  user_name               TEXT,
  user_role_id            TEXT,
  school_id_csv           TEXT,
  course_nid              TEXT,
  section_nid             TEXT,
  section_code            TEXT,
  item_id                 TEXT,
  item_name               TEXT,
  first_access            TIMESTAMPTZ,
  latest_attempt          TIMESTAMPTZ,
  total_time              INTERVAL,
  submission_grade        NUMERIC(10,4),
  submission              INTEGER,
  question_id             TEXT,
  session                 TEXT,
  assessment_type         TEXT,
  subject                 TEXT,
  grade                   TEXT,
  section                 TEXT,
  file_name               TEXT,
  position_number         TEXT,
  sub_question            TEXT,
  answer_submission       TEXT,
  correct_answer          TEXT,
  points_received         NUMERIC(10,4),
  points_possible         NUMERIC(10,4),
  user_id_ques_id         TEXT,
  grade_id                TEXT,
  assessment_id           TEXT,
  subject_id              TEXT,
  strand_id               TEXT,
  standard                TEXT,
  identifier              TEXT
);
CREATE INDEX fact_student_submission_school_idx       ON fact_student_submission (school_id);
CREATE INDEX fact_student_submission_school_item_idx  ON fact_student_submission (school_id, item_id);
CREATE INDEX fact_student_submission_school_question_idx ON fact_student_submission (school_id, question_id);
CREATE INDEX fact_student_submission_school_user_idx  ON fact_student_submission (school_id, user_uid);
CREATE INDEX fact_student_submission_school_subject_idx ON fact_student_submission (school_id, subject_id);
CREATE INDEX fact_student_submission_identifier_idx   ON fact_student_submission (identifier);
