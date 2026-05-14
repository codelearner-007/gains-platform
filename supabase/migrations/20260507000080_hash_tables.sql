-- Pseudonymized companion tables (notebook lines 1295-1320).
-- Naming kept lowercase per Postgres convention.

-- I18 — UNIQUE (school_id, *_hash) makes the rename guarantee explicit so two
-- hash collisions cannot land in one tenant. Composite index on the lookup
-- columns is the right shape for tenant-scoped joins.
CREATE TABLE dim_section_hash (
  section_nid          TEXT NOT NULL,
  school_id            UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  section_instructors  TEXT,
  teacher_name_hash    TEXT,
  PRIMARY KEY (school_id, section_nid),
  UNIQUE (school_id, teacher_name_hash)
);
CREATE INDEX dim_section_hash_school_idx ON dim_section_hash (school_id);
CREATE INDEX dim_section_hash_teacher_idx ON dim_section_hash (school_id, teacher_name_hash);

CREATE TABLE dim_student_hash (
  user_uid           TEXT NOT NULL,
  school_id          UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  user_name          TEXT,
  student_name_hash  TEXT,
  PRIMARY KEY (school_id, user_uid),
  UNIQUE (school_id, student_name_hash)
);
CREATE INDEX dim_student_hash_school_idx ON dim_student_hash (school_id);
CREATE INDEX dim_student_hash_student_idx ON dim_student_hash (school_id, student_name_hash);

-- fact_student_submissions_hash mirrors fact_student_submission row-for-row
-- with student name swapped for hash. Use LIKE INCLUDING ALL to keep schema
-- in lockstep with the fact table; the user_name column is repurposed at
-- write time with the StudentName_Hash value.
CREATE TABLE fact_student_submissions_hash (
  LIKE fact_student_submission INCLUDING DEFAULTS INCLUDING CONSTRAINTS
);
ALTER TABLE fact_student_submissions_hash
  ADD COLUMN student_name_hash TEXT;
ALTER TABLE fact_student_submissions_hash
  ADD CONSTRAINT fact_student_submissions_hash_pkey PRIMARY KEY (user_id_ques_id_stand);
ALTER TABLE fact_student_submissions_hash
  ADD CONSTRAINT fact_student_submissions_hash_school_fk
  FOREIGN KEY (school_id) REFERENCES schools(school_id) ON DELETE CASCADE;
CREATE INDEX fact_student_submissions_hash_school_idx       ON fact_student_submissions_hash (school_id);
CREATE INDEX fact_student_submissions_hash_school_item_idx  ON fact_student_submissions_hash (school_id, item_id);
CREATE INDEX fact_student_submissions_hash_school_question_idx ON fact_student_submissions_hash (school_id, question_id);
CREATE INDEX fact_student_submissions_hash_school_user_idx  ON fact_student_submissions_hash (school_id, user_uid);
CREATE INDEX fact_student_submissions_hash_student_hash_idx ON fact_student_submissions_hash (student_name_hash);
