-- HMH-curriculum tenant seed (dev/bootstrap).
--
-- Registers a GAINS tenant whose assessment data is ingested from HMH Ed's
-- native CSV exports (School Data Export → "Assessed Standards Results"), NOT
-- from Schoology. Schools on HMH never appear in a Schoology building, so the
-- Schoology-shaped identity columns carry HMH sentinels instead:
--
--   schoology_building_id / schoology_school_id : 'hmh-<HMH school_pid>'
--       The 'hmh-' prefix is self-documenting and collision-proof against the
--       numeric Schoology building ids ('186370968' etc.). staging resolves a
--       row's tenant via schools.schoology_school_id = user_school_id, so the
--       HMH parser stamps every row's user_school_id with this exact value.
--   student_role_id : 'hmh-student'
--       Schoology assigns a numeric Student role id per building; HMH has no
--       such concept. The parser emits user_role_id='hmh-student' on every row,
--       matching this column, so the "students only" fact filter
--       (user_role_id = schools.student_role_id) admits HMH rows. Both sides
--       come from this one row, so they cannot drift.
--
-- HMH identity crosswalk for this pilot tenant (from the AAOTA export):
--   HMH school_pid   = 10030164
--   HMH school_refid = fc945278-0074-4be2-95a8-dee251f16891
--   LMS              = none (assessments taken natively in HMH Ed)
--
-- The scraper-only columns (category_regex, due_date_window_days,
-- course_page_limit, download_index, category_folder_override) are inert for a
-- CSV-export ingest and are set to sensible defaults for schema completeness.
--
-- Applied manually (tier-2), NOT wired into supabase/config.toml sql_paths;
-- schools_all.sql is left untouched. Idempotent via
-- ON CONFLICT (schoology_building_id) DO UPDATE.

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
    'hmh-10030164', 'hmh-10030164',
    'Athenian Academy (HMH)', 'AthenianHMH',
    'hmh-student',
    '(Chapter|lesson|Weekly|Module|Assessments)',
    14, 200, '[1,2,3]'::jsonb, NULL,
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
