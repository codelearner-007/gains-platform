-- Co-teacher pair -> primary teacher overrides.
-- Source: Schoology_py.ipynb lines 354-413 (teacher_dict_athenian /
-- teacher_dict_brightview / teacher_dict_southprep).
-- We resolve school_id via subquery on schoology_building_id so this seed is
-- robust to UUID v7 values minted at insert time. Rows whose school is not
-- yet onboarded are skipped (the WHERE filter on the subquery).

-- Athenian (schoology_building_id = '186370968')
INSERT INTO public.teacher_pair_overrides (school_id, pair_pattern, primary_teacher)
SELECT s.school_id, v.pair_pattern, v.primary_teacher
FROM (VALUES
  ('Evan Markowitz, Jannette Rivera',                   'Jannette Rivera'),
  ('Maria Baclohan, Evan Markowitz',                    'Maria Baclohan'),
  ('Evan Markowitz, Mason Reeder',                      'Mason Reeder'),
  ('Melaina Fijalkowski, Kathleen Tsakonas',            'Kathleen Tsakonas'),
  ('Evan Markowitz, Elizabeth Sedlak',                  'Elizabeth Sedlak'),
  ('Daniel Smith, Nicole Swidarski',                    'Nicole Swidarski'),
  ('Susanna Birdwell, Evan Markowitz',                  'Susanna Birdwell'),
  ('Evan Markowitz, Niki Paul',                         'Niki Paul'),
  ('Evan Markowitz, Tiffany Schaefer',                  'Tiffany Schaefer'),
  ('Evan Markowitz, Kathleen Tsakonas',                 'Kathleen Tsakonas'),
  ('Susanna Birdwell, Melaina Fijalkowski',             'Susanna Birdwell'),
  ('Daniel Smith, Heather Watkins',                     'Heather Watkins'),
  ('Evan Markowitz, Mary Sidhom',                       'Mary Sidhom'),
  ('Carissa Farrell, Madison Wahn',                     'Carissa Farrell'),
  ('Mary Sidhom, Madison Wahn',                         'Madison Wahn'),
  ('Evan Markowitz, Pattie Rossi',                      'Pattie Rossi'),
  ('Gabriela Agostino, Sitara Qalander',                'Gabriela Agostino'),
  ('Sharon Long, Pattie Rossi',                         'Pattie Rossi'),
  ('Ana Leiva, Mary Vaughn',                            'Mary Vaughn'),
  ('Evan Markowitz, Sitara Qalander, Jannette Rivera',  'Jannette Rivera'),
  ('Maria Baclohan, Sharon Long',                       'Maria Baclohan'),
  ('Gabriela Agostino, Evan Markowitz',                 'Gabriela Agostino'),
  ('Ashley Lekhram, Evan Markowitz',                    'Ashley Lekhram'),
  ('Ana Leiva, Evan Markowitz, Mary Vaughn',            'Ana Leiva'),
  ('Evan Markowitz, Nicole Swidarski',                  'Nicole Swidarski'),
  ('Carissa Farrell, Evan Markowitz',                   'Carissa Farrell'),
  ('Elizabeth Bennet, Melaina Fijalkowski',             'Elizabeth Bennet'),
  ('Melaina Fijalkowski, Nicole Swidarski',             'Nicole Swidarski'),
  ('Maria Baclohan, Sitara Qalander',                   'Maria Baclohan'),
  ('Taylor Almendinger, Mason Reeder, Elizabeth Sedlak','Taylor Almendinger'),
  ('Sitara Qalander, Elizabeth Sedlak',                 'Elizabeth Sedlak')
) AS v(pair_pattern, primary_teacher)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '186370968') s
ON CONFLICT (school_id, pair_pattern) DO NOTHING;

-- Brightview (schoology_building_id = '7448280461')
INSERT INTO public.teacher_pair_overrides (school_id, pair_pattern, primary_teacher)
SELECT s.school_id, v.pair_pattern, v.primary_teacher
FROM (VALUES
  ('Heather Fernandez, Rommy Rodriguez, Arian Rubio',   'Arian Rubio'),
  ('Rommy Rodriguez, Arian Rubio',                      'Arian Rubio'),
  ('Elizabeth McKinney, Rommy Rodriguez',               'Elizabeth McKinney'),
  ('Kenia Gomez, Rommy Rodriguez',                      'Kenia Gomez'),
  ('Elizabeth McKinney, Melba Montano, Rommy Rodriguez','Melba Montano'),
  ('Kenia Gomez, Jannette Rivera, Rommy Rodriguez',     'Kenia Gomez'),
  ('Dayanis Ceballo, Rommy Rodriguez',                  'Dayanis Ceballo'),
  ('Melba Montano, Rommy Rodriguez',                    'Melba Montano')
) AS v(pair_pattern, primary_teacher)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '7448280461') s
ON CONFLICT (school_id, pair_pattern) DO NOTHING;

-- SouthPrep (schoology_building_id = '7368546879')
INSERT INTO public.teacher_pair_overrides (school_id, pair_pattern, primary_teacher)
SELECT s.school_id, v.pair_pattern, v.primary_teacher
FROM (VALUES
  ('Dayanis Ceballo, Rommy Rodriguez', 'Dayanis Ceballo')
) AS v(pair_pattern, primary_teacher)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '7368546879') s
ON CONFLICT (school_id, pair_pattern) DO NOTHING;
