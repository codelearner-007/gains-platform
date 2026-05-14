-- Athenian Academy of Technology and the Arts seed row.
-- The two-space gap in category_folder_override ('1 - Lesson  Assessments') is
-- intentional: that is the literal folder name used in Azure Blob storage.

INSERT INTO public.schools (
  schoology_building_id,
  schoology_school_id,
  name,
  short_name,
  category_regex,
  due_date_window_days,
  course_page_limit,
  download_index,
  category_folder_override,
  timezone,
  current_session,
  is_active
) VALUES (
  '186370968',
  '186370968',
  'Athenian Academy of Technology and the Arts',
  'Athenian',
  '(Chapter|lesson|Weekly|Module|Assessments)',
  14,
  200,
  '[1,2,3]'::jsonb,
  '1 - Lesson  Assessments',
  'America/New_York',
  '2025-26',
  TRUE
)
ON CONFLICT (schoology_building_id) DO NOTHING;
