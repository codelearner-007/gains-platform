-- All active GAINS schools (dev/bootstrap seed).
--
-- Replaces schools_athenian.sql in config.toml [db.seed].sql_paths. A clean
-- `supabase db reset` reproduces the full 5-school platform so per-school
-- transforms, teacher_pair_overrides, and the report school-switcher all
-- resolve. In PRODUCTION schools are onboarded via the tenancy control plane,
-- not this seed; treat it as a dev reproducibility fixture.
--
-- Identity + per-school student role come from a discovery pass over the legacy
-- backup's Student-Submissions CSVs (distinct User School ID / User School Name /
-- Student User Role ID). Schoology assigns a different Student role id per
-- building, so each row carries its own student_role_id (Athenian = 286170,
-- which keeps Athenian's existing dim/fact/cube rows byte-identical).
--
-- The two-space gap in category_folder_override ('1 - Lesson  Assessments') is
-- intentional: that is the literal folder name used in Azure Blob storage.
--
-- ON CONFLICT (schoology_building_id) DO UPDATE keeps this idempotent and aligns
-- existing rows (e.g. the LIVE Athenian row) with the values below on re-seed.

INSERT INTO public.schools (
  schoology_building_id,
  schoology_school_id,
  name,
  short_name,
  student_role_id,
  category_regex,
  due_date_window_days,
  course_page_limit,
  download_index,
  category_folder_override,
  timezone,
  current_session,
  is_active
) VALUES
  (
    '186370968', '186370968',
    'Athenian Academy of Technology and the Arts', 'Athenian',
    '286170',
    '(Chapter|lesson|Weekly|Module|Assessments)',
    14, 200, '[1,2,3]'::jsonb, '1 - Lesson  Assessments',
    'America/New_York', '2025-26', TRUE
  ),
  (
    '554425139', '554425139',
    'Central Florida Preparatory School', 'CFP',
    '320939',
    '(Chapter|lesson|Weekly|Module|Assessments)',
    14, 200, '[1,2,3]'::jsonb, '1 - Lesson  Assessments',
    'America/New_York', '2025-26', TRUE
  ),
  (
    '7368546879', '7368546879',
    'South Prep Scholars Academy', 'SouthPrep',
    '925819',
    '(Chapter|lesson|Weekly|Module|Assessments)',
    14, 200, '[1,2,3]'::jsonb, '1 - Lesson  Assessments',
    'America/New_York', '2025-26', TRUE
  ),
  (
    '7440430446', '7440430446',
    'Crestwell School', 'Crestwell',
    '927486',
    '(Chapter|lesson|Weekly|Module|Assessments)',
    14, 200, '[1,2,3]'::jsonb, '1 - Lesson  Assessments',
    'America/New_York', '2025-26', TRUE
  ),
  (
    '7448280461', '7448280461',
    'Brightview Prep', 'Brightview',
    '927606',
    '(Chapter|lesson|Weekly|Module|Assessments)',
    14, 200, '[1,2,3]'::jsonb, '1 - Lesson  Assessments',
    'America/New_York', '2025-26', TRUE
  )
ON CONFLICT (schoology_building_id) DO UPDATE
SET schoology_school_id      = EXCLUDED.schoology_school_id,
    name                     = EXCLUDED.name,
    short_name               = EXCLUDED.short_name,
    student_role_id          = EXCLUDED.student_role_id,
    category_regex           = EXCLUDED.category_regex,
    due_date_window_days     = EXCLUDED.due_date_window_days,
    course_page_limit        = EXCLUDED.course_page_limit,
    download_index           = EXCLUDED.download_index,
    category_folder_override = EXCLUDED.category_folder_override,
    timezone                 = EXCLUDED.timezone,
    current_session          = EXCLUDED.current_session,
    is_active                = EXCLUDED.is_active,
    updated_at               = now();
