CREATE TABLE schools (
  school_id                  UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  schoology_building_id      TEXT UNIQUE NOT NULL,
  schoology_school_id        TEXT UNIQUE,
  edvance_tenant_id          TEXT,
  name                       TEXT NOT NULL,
  short_name                 TEXT NOT NULL,
  logo_url                   TEXT,
  category_regex             TEXT NOT NULL DEFAULT '(Chapter|lesson|Weekly|Module|Assessments)',
  due_date_window_days       INTEGER NOT NULL DEFAULT 14,
  course_page_limit          INTEGER NOT NULL DEFAULT 200,
  download_index             JSONB NOT NULL DEFAULT '[1,2,3]',
  item_filter_expression     TEXT DEFAULT '',
  category_folder_override   TEXT,
  current_session            TEXT,
  timezone                   TEXT NOT NULL DEFAULT 'America/New_York',
  is_active                  BOOLEAN NOT NULL DEFAULT TRUE,
  created_at                 TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at                 TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX schools_schoology_school_id_idx ON schools (schoology_school_id);
CREATE INDEX schools_is_active_idx ON schools (is_active);

CREATE TABLE subject_overrides (
  override_id        UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  school_id          UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  grade              TEXT NOT NULL,
  subject_match      TEXT NOT NULL,
  subject_override   TEXT NOT NULL,
  source             TEXT NOT NULL DEFAULT 'edvance_api',
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (school_id, grade, subject_match)
);
CREATE INDEX subject_overrides_school_idx ON subject_overrides (school_id);

CREATE TABLE subject_course_overrides (
  override_id              UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  school_id                UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  course_name_match_regex  TEXT NOT NULL,
  subject_override         TEXT NOT NULL,
  source                   TEXT NOT NULL DEFAULT 'edvance_api',
  created_at               TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (school_id, course_name_match_regex)
);
CREATE INDEX subject_course_overrides_school_idx ON subject_course_overrides (school_id);

CREATE TABLE teacher_pair_overrides (
  override_id        UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  school_id          UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  pair_pattern       TEXT NOT NULL,
  primary_teacher    TEXT NOT NULL,
  created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (school_id, pair_pattern)
);
CREATE INDEX teacher_pair_overrides_school_idx ON teacher_pair_overrides (school_id);

CREATE TABLE school_grade_overrides (
  override_id    UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  school_id      UUID NOT NULL REFERENCES schools(school_id) ON DELETE CASCADE,
  grade_match    TEXT[] NOT NULL,
  grade_override TEXT NOT NULL,
  created_at     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (school_id, grade_override)
);
CREATE INDEX school_grade_overrides_school_idx ON school_grade_overrides (school_id);
