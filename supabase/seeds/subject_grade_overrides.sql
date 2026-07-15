-- =============================================================================
-- Subject / grade normalization overrides (per-tenant)
--
-- WHY: subject & grade in this platform are derived from the Schoology export
-- FOLDER names (file_path_parser.py: subject=parts[-4], grade=parts[-3]). The
-- raw backup tree uses inconsistent folder naming across export batches:
--   * 2024-25  numeric-prefixed:  "1 - Math", "4 - ELA", "0 - Grade K"
--   * 2025-26  download-renamed:   "Mathematics", "Language Arts", "Other",
--                                   "Grade K", plus placeholders "No grade level"
-- Without normalization every variant survives into dim_subject/dim_grade, so the
-- dashboard slicers show duplicates (1 - ELA, ELA, Language Arts, … all distinct).
--
-- Legacy collapsed these to canonical ELA/Math/Science(/…) + Grade K-8 in TWO
-- layers; this seed pre-composes both into the single exact-match override pass
-- the staging step (stg_student_submission.sql / stg_question_data.sql) performs:
--   Layer A — folder→canonical  (SubjectMap / GradeMap, applied at Schoology
--             DOWNLOAD time in legacy): "1 - Math"→Mathematics, "4 - ELA"→Other/
--             Language Arts, "0 - Grade K"→Grade K.
--   Layer B — per-tenant overrides (SubjectOverrideConfigJson /
--             MapSubjectWithCourseNameJson + hardcoded CFP grade remap), applied
--             in the legacy Spark notebook (Schoology_py.ipynb L204-303).
--
-- SOURCE OF TRUTH (authentic, verbatim): the legacy EdvanceLearning Reporting
-- backend's ABP settings store, recovered by restoring
--   legacy-backup-20260529/mssql/{Administration,Saas}.bak
-- into SQL Server 2022 and reading Administration.dbo.AbpSettings
-- (keys SubjectOverrideConfigJson / MapSubjectWithCourseNameJson / SubjectMap /
-- GradeMap, per tenant GUID). The "Regular 9–12" grade remap is NOT in AbpSettings;
-- it is hardcoded in the notebook for CFP only (en-dash U+2013).
--   Full extracts: data/_pbix_extract/  /  .tmp_audit/research_tenant_config.md
--
-- TENANT GUID ↔ Schoology building id ↔ school:
--   186370968  Athenian   (21b55d48-bdb4-533a-94c2-3a131ec91407)
--   554425139  CFP        (1866761e-2845-3bbd-7add-3a17c84c5872)
--   7440430446 Crestwell  (99a93bb7-2d4b-996a-ffbd-3a163cd06a12) — Other/LangArts → Reading
--   7368546879 SouthPrep  (96646d4f-…) — not in prod, no-ops
--   7448280461 Brightview (d7607eab-…) — empty override set, no-ops
--
-- MATCH SEMANTICS (mirrors staging joins):
--   subject_overrides       : so.grade = rss.grade AND so.subject_match = rss.subject
--                             (RAW folder values incl. numeric prefix). Therefore
--                             rows are emitted for BOTH the prefixed ("0 - Grade K")
--                             and clean ("Grade K") raw-grade variant of each rule.
--   subject_course_overrides: rss.course_name ~ regex, FIRST by override_id
--                             (inserted longest-pattern-first so "HS English II"
--                             wins over the "HS English I" substring). CFP only;
--                             stg_student_submission only (question_data has no
--                             course_name).
--   school_grade_overrides  : rss.grade = ANY(grade_match[]) → grade_override.
--
-- School resolution: subquery on schoology_building_id (mirrors
-- teacher_pair_overrides.sql); rows for non-onboarded schools silently no-op.
--
-- DEVIATIONS from a byte-for-byte legacy CUBE mirror are marked  -- DEVIATION.
-- Legacy left a few un-mapped folders (e.g. Athenian "1 - ELA", "2 - Reading")
-- as residue in its cube and hid them at the PowerBI slicer layer; this platform
-- has no such slicer layer, so to reproduce the clean legacy DASHBOARD slicer we
-- map them to the canonical their grade dictates. Delete the DEVIATION rows for
-- pure cube parity.
-- =============================================================================


-- =============================================================================
-- 1. subject_overrides  (school_id, grade, subject_match, subject_override)
-- =============================================================================

-- ---- ATHENIAN (186370968) ---------------------------------------------------
INSERT INTO public.subject_overrides (school_id, grade, subject_match, subject_override, source)
SELECT s.school_id, gv.raw_grade, r.subject_match, r.subject_override, 'edvance_api'
FROM (VALUES
  -- Layer-B (clean 2025-26 folder names) — verbatim SubjectOverrideConfigJson
  ('Grade K','Other','ELA'),
  ('Grade 1','Other','ELA'),
  ('Grade 2','Other','ELA'),
  ('Grade 3','Other','ELA'),
  ('Grade 4','Other','ELA'),
  ('Grade 5','Other','ELA'),
  ('Grade 1','Language Arts','ELA'),
  ('Grade 6','Language Arts','ELA'),
  ('Grade 7','Language Arts','ELA'),
  ('Grade 8','Language Arts','ELA'),
  ('Grade K','Mathematics','Math'),
  ('Grade 1','Mathematics','Math'),
  ('Grade 2','Mathematics','Math'),
  ('Grade 3','Mathematics','Math'),
  ('Grade 4','Mathematics','Math'),
  ('Grade 5','Mathematics','Math'),
  ('Grade 6','Mathematics','Math'),
  ('Grade 7','Mathematics','Math'),
  ('Grade 8','Mathematics','Algebra'),
  ('Grade 6','Social Studies','History'),
  ('Grade 7','Social Studies','History'),
  ('Grade 8','Social Studies','Civics'),
  -- Layer-A composed (2024-25 numeric folders). Athenian SubjectMap:
  --   1 - Math→Mathematics ; 3 - Science→Science ; 4 - ELA→Other/Language Arts ; 5 - History→Social Studies
  ('Grade K','1 - Math','Math'),
  ('Grade 1','1 - Math','Math'),
  ('Grade 2','1 - Math','Math'),
  ('Grade 3','1 - Math','Math'),
  ('Grade 4','1 - Math','Math'),
  ('Grade 5','1 - Math','Math'),
  ('Grade 6','1 - Math','Math'),
  ('Grade 7','1 - Math','Math'),
  ('Grade 8','1 - Math','Algebra'),
  ('Grade K','4 - ELA','ELA'),
  ('Grade 1','4 - ELA','ELA'),
  ('Grade 2','4 - ELA','ELA'),
  ('Grade 3','4 - ELA','ELA'),
  ('Grade 4','4 - ELA','ELA'),
  ('Grade 5','4 - ELA','ELA'),
  ('Grade 6','4 - ELA','ELA'),
  ('Grade 7','4 - ELA','ELA'),
  ('Grade 8','4 - ELA','ELA'),
  ('Grade K','3 - Science','Science'),
  ('Grade 1','3 - Science','Science'),
  ('Grade 2','3 - Science','Science'),
  ('Grade 3','3 - Science','Science'),
  ('Grade 4','3 - Science','Science'),
  ('Grade 5','3 - Science','Science'),
  ('Grade 6','3 - Science','Science'),
  ('Grade 7','3 - Science','Science'),
  ('Grade 8','3 - Science','Science'),
  ('Grade 6','5 - History','History'),
  ('Grade 7','5 - History','History'),
  ('Grade 8','5 - History','Civics'),
  ('Grade 1','5 - History','Social Studies'),
  ('Grade 3','5 - History','Social Studies'),
  ('Grade 4','5 - History','Social Studies'),
  -- DEVIATION: folders absent from Athenian SubjectMap (legacy cube residue),
  -- mapped to the canonical their grade dictates for a clean slicer.
  ('Grade K','1 - ELA','ELA'),               -- DEVIATION
  ('Grade 1','1 - ELA','ELA'),               -- DEVIATION
  ('Grade 2','1 - ELA','ELA'),               -- DEVIATION
  ('Grade 3','1 - ELA','ELA'),               -- DEVIATION
  ('Grade 4','1 - ELA','ELA'),               -- DEVIATION
  ('Grade 5','1 - ELA','ELA'),               -- DEVIATION
  ('Grade 6','1 - ELA','ELA'),               -- DEVIATION
  ('Grade 7','1 - ELA','ELA'),               -- DEVIATION
  ('Grade 8','1 - ELA','ELA'),               -- DEVIATION
  ('Grade K','2 - Reading','ELA'),           -- DEVIATION
  ('Grade 1','2 - Reading','ELA'),           -- DEVIATION
  ('Grade 2','2 - Reading','ELA'),           -- DEVIATION
  ('Grade 3','2 - Reading','ELA'),           -- DEVIATION
  ('Grade 4','2 - Reading','ELA'),           -- DEVIATION
  ('Grade 5','2 - Reading','ELA'),           -- DEVIATION
  ('Grade 6','5 - Social Studies','History'),-- DEVIATION
  ('Grade 8','5 - Social Studies','Civics')  -- DEVIATION
) AS r(clean_grade, subject_match, subject_override)
CROSS JOIN LATERAL (VALUES
  (r.clean_grade),
  (CASE r.clean_grade
     WHEN 'Grade K' THEN '0 - Grade K' WHEN 'Grade 1' THEN '1 - Grade 1'
     WHEN 'Grade 2' THEN '2 - Grade 2' WHEN 'Grade 3' THEN '3 - Grade 3'
     WHEN 'Grade 4' THEN '4 - Grade 4' WHEN 'Grade 5' THEN '5 - Grade 5'
     WHEN 'Grade 6' THEN '6 - Grade 6' WHEN 'Grade 7' THEN '7 - Grade 7'
     WHEN 'Grade 8' THEN '8 - Grade 8' END)
) AS gv(raw_grade)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '186370968') s
WHERE gv.raw_grade IS NOT NULL
ON CONFLICT (school_id, grade, subject_match) DO NOTHING;


-- ---- CFP (554425139) --------------------------------------------------------
INSERT INTO public.subject_overrides (school_id, grade, subject_match, subject_override, source)
SELECT s.school_id, gv.raw_grade, r.subject_match, r.subject_override, 'edvance_api'
FROM (VALUES
  -- Layer-B (clean) — verbatim SubjectOverrideConfigJson
  ('Grade K','Mathematics','Math'),
  ('Grade 1','Mathematics','Math'),
  ('Grade 2','Mathematics','Math'),
  ('Grade 3','Mathematics','Math'),
  ('Grade 4','Mathematics','Math'),
  ('Grade 5','Mathematics','Math'),
  ('Grade 6','Mathematics','Math'),
  ('Grade 7','Mathematics','Math'),
  ('Grade 8','Mathematics','Algebra'),
  ('Grade K','Other','ELA'),
  ('Grade 1','Other','ELA'),
  ('Grade 2','Other','ELA'),
  ('Grade 3','Other','ELA'),
  ('Grade 4','Other','ELA'),
  ('Grade 5','Other','ELA'),
  ('Grade 6','Other','ELA'),
  ('Grade 7','Other','ELA'),
  ('Grade 8','Other','ELA'),
  ('Grade K','Language Arts','ELA'),
  ('Grade 1','Language Arts','ELA'),
  ('Grade 2','Language Arts','ELA'),
  ('Grade 3','Language Arts','ELA'),
  ('Grade 4','Language Arts','ELA'),
  ('Grade 5','Language Arts','ELA'),
  ('Grade 6','Language Arts','ELA'),
  ('Grade 7','Language Arts','ELA'),
  ('Grade 8','Language Arts','ELA'),
  ('Grade 6','Social Studies','History'),
  ('Grade 7','Social Studies','Civics'),
  ('Grade 8','Social Studies','History'),
  -- Layer-A composed (2024-25 numeric). CFP SubjectMap same shape as Athenian.
  ('Grade K','1 - Math','Math'),
  ('Grade 1','1 - Math','Math'),
  ('Grade 2','1 - Math','Math'),
  ('Grade 3','1 - Math','Math'),
  ('Grade 4','1 - Math','Math'),
  ('Grade 5','1 - Math','Math'),
  ('Grade 6','1 - Math','Math'),
  ('Grade 7','1 - Math','Math'),
  ('Grade 8','1 - Math','Algebra'),
  ('Grade 1','3 - Science','Science'),
  ('Grade 2','3 - Science','Science'),
  ('Grade 3','3 - Science','Science'),
  ('Grade 4','3 - Science','Science'),
  ('Grade 5','3 - Science','Science'),
  ('Grade 6','3 - Science','Science'),
  ('Grade 7','3 - Science','Science'),
  ('Grade 8','3 - Science','Science'),
  ('Grade 2','4 - ELA','ELA'),
  ('Grade 3','4 - ELA','ELA'),
  ('Grade 6','4 - ELA','ELA'),
  ('Grade 7','4 - ELA','ELA'),
  ('Grade 8','4 - ELA','ELA'),
  ('Grade 6','5 - History','History'),
  ('Grade 7','5 - History','Civics'),
  ('Grade 8','5 - History','History')
) AS r(clean_grade, subject_match, subject_override)
CROSS JOIN LATERAL (VALUES
  (r.clean_grade),
  (CASE r.clean_grade
     WHEN 'Grade K' THEN '0 - Grade K' WHEN 'Grade 1' THEN '1 - Grade 1'
     WHEN 'Grade 2' THEN '2 - Grade 2' WHEN 'Grade 3' THEN '3 - Grade 3'
     WHEN 'Grade 4' THEN '4 - Grade 4' WHEN 'Grade 5' THEN '5 - Grade 5'
     WHEN 'Grade 6' THEN '6 - Grade 6' WHEN 'Grade 7' THEN '7 - Grade 7'
     WHEN 'Grade 8' THEN '8 - Grade 8' END)
) AS gv(raw_grade)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '554425139') s
WHERE gv.raw_grade IS NOT NULL
ON CONFLICT (school_id, grade, subject_match) DO NOTHING;

-- CFP high-school supplement: numeric folders at 9-12 + clean-subject FALLBACKS at
-- 9-12 / Higher-Ed. The CFP course-name overrides (section 2) SUPERSEDE these via the
-- staging COALESCE(sco, so, raw) order — these apply only when no HS course-name matches,
-- so the slicer never shows residual "Mathematics"/"Language Arts"/"Other"/numeric at HS.
INSERT INTO public.subject_overrides (school_id, grade, subject_match, subject_override, source)
SELECT s.school_id, gv.raw_grade, r.subject_match, r.subject_override, 'edvance_api'
FROM (VALUES
  ('Grade 9','1 - Math','Math'),
  ('Grade 9','4 - ELA','ELA'),
  ('Grade 10','4 - ELA','ELA'),
  ('Grade 11','4 - ELA','ELA'),
  ('Grade 12','4 - ELA','ELA'),
  ('Grade 9','Mathematics','Math'),
  ('Grade 10','Mathematics','Math'),
  ('Grade 11','Mathematics','Math'),
  ('Grade 12','Mathematics','Math'),
  ('Higher-Ed','Mathematics','Math'),
  ('Grade 9','Language Arts','ELA'),
  ('Grade 10','Language Arts','ELA'),
  ('Grade 11','Language Arts','ELA'),
  ('Grade 12','Language Arts','ELA'),
  ('Higher-Ed','Language Arts','ELA'),
  ('Higher-Ed','Other','ELA'),
  ('Higher-Ed','Social Studies','History')
) AS r(clean_grade, subject_match, subject_override)
CROSS JOIN LATERAL (VALUES
  (r.clean_grade),
  (CASE r.clean_grade
     WHEN 'Grade 9' THEN '9 - Grade 9'   WHEN 'Grade 10' THEN '10 - Grade 10'
     WHEN 'Grade 11' THEN '11 - Grade 11' WHEN 'Grade 12' THEN '12 - Grade 12'
     ELSE NULL END)
) AS gv(raw_grade)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '554425139') s
WHERE gv.raw_grade IS NOT NULL
ON CONFLICT (school_id, grade, subject_match) DO NOTHING;


-- ---- CRESTWELL (7440430446) — Other/Language Arts → READING -----------------
INSERT INTO public.subject_overrides (school_id, grade, subject_match, subject_override, source)
SELECT s.school_id, gv.raw_grade, r.subject_match, r.subject_override, 'edvance_api'
FROM (VALUES
  ('Grade K','Other','Reading'),
  ('Grade 1','Other','Reading'),
  ('Grade 2','Other','Reading'),
  ('Grade 3','Other','Reading'),
  ('Grade 4','Other','Reading'),
  ('Grade 5','Other','Reading'),
  ('Grade 6','Other','Reading'),
  ('Grade 7','Other','Reading'),
  ('Grade 8','Other','Reading'),
  ('Grade K','Language Arts','Reading'),
  ('Grade 1','Language Arts','Reading'),
  ('Grade 2','Language Arts','Reading'),
  ('Grade 3','Language Arts','Reading'),
  ('Grade 4','Language Arts','Reading'),
  ('Grade 5','Language Arts','Reading'),
  ('Grade 6','Language Arts','Reading'),
  ('Grade 7','Language Arts','Reading'),
  ('Grade 8','Language Arts','Reading'),
  -- 2025-26 download renamed Crestwell's Reading folder set to the literal
  -- raw subject "ELA" (this backup ships Summative/ELA/ AND Summative/Reading/
  -- copies of the SAME physical assessments — e.g. "Module Assessment: Be a
  -- Super Citizen", same 16 students/section, same 17 questions). Legacy folds
  -- the ELA-family into Reading (Crestwell's canonical subjects are
  -- Reading/Math/Science/History — there is NO standalone ELA). Without this
  -- the duplicate "ELA" subject_id surfaces a phantom ELA tile on the dashboard
  -- and double-counts (GAI-13). All 14 Crestwell ELA items already exist as
  -- same-name/grade Reading items, so uuid_6 merges them losslessly into the
  -- existing Reading subject_id.
  ('Grade K','ELA','Reading'),
  ('Grade 1','ELA','Reading'),
  ('Grade 2','ELA','Reading'),
  ('Grade 3','ELA','Reading'),
  ('Grade 4','ELA','Reading'),
  ('Grade 5','ELA','Reading'),
  ('Grade 6','ELA','Reading'),
  ('Grade 7','ELA','Reading'),
  ('Grade 8','ELA','Reading'),
  ('Grade K','Mathematics','Math'),
  ('Grade 1','Mathematics','Math'),
  ('Grade 2','Mathematics','Math'),
  ('Grade 3','Mathematics','Math'),
  ('Grade 4','Mathematics','Math'),
  ('Grade 5','Mathematics','Math'),
  ('Grade 6','Mathematics','Math'),
  ('Grade 7','Mathematics','Math'),
  ('Grade 8','Mathematics','Math'),
  ('Grade K','Social Studies','History'),
  ('Grade 1','Social Studies','History'),
  ('Grade 2','Social Studies','History'),
  ('Grade 3','Social Studies','History'),
  ('Grade 4','Social Studies','History'),
  ('Grade 5','Social Studies','History'),
  ('Grade 6','Social Studies','History'),
  ('Grade 7','Social Studies','History'),
  ('Grade 8','Social Studies','History'),
  -- Layer-A composed (2024-25 numeric). Crestwell SubjectMap:
  --   1 - Math→Mathematics ; 3 - Science→Science ; 2 - Reading→Other/Language Arts(→Reading) ; 5 - History→Social Studies
  ('Grade K','1 - Math','Math'),
  ('Grade 1','1 - Math','Math'),
  ('Grade 2','1 - Math','Math'),
  ('Grade 3','1 - Math','Math'),
  ('Grade 4','1 - Math','Math'),
  ('Grade 5','1 - Math','Math'),
  ('Grade K','2 - Reading','Reading'),
  ('Grade 1','2 - Reading','Reading'),
  ('Grade 2','2 - Reading','Reading'),
  ('Grade 3','2 - Reading','Reading'),
  ('Grade 4','2 - Reading','Reading'),
  ('Grade 5','2 - Reading','Reading'),
  ('Grade 8','2 - Reading','Reading'),
  ('Grade K','3 - Science','Science'),
  ('Grade 1','3 - Science','Science'),
  ('Grade 2','3 - Science','Science'),
  ('Grade 3','3 - Science','Science'),
  ('Grade 4','3 - Science','Science'),
  ('Grade 5','3 - Science','Science'),
  ('Grade 6','3 - Science','Science'),
  ('Grade 7','3 - Science','Science'),
  ('Grade 8','3 - Science','Science')
) AS r(clean_grade, subject_match, subject_override)
CROSS JOIN LATERAL (VALUES
  (r.clean_grade),
  (CASE r.clean_grade
     WHEN 'Grade K' THEN '0 - Grade K' WHEN 'Grade 1' THEN '1 - Grade 1'
     WHEN 'Grade 2' THEN '2 - Grade 2' WHEN 'Grade 3' THEN '3 - Grade 3'
     WHEN 'Grade 4' THEN '4 - Grade 4' WHEN 'Grade 5' THEN '5 - Grade 5'
     WHEN 'Grade 6' THEN '6 - Grade 6' WHEN 'Grade 7' THEN '7 - Grade 7'
     WHEN 'Grade 8' THEN '8 - Grade 8' END)
) AS gv(raw_grade)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '7440430446') s
WHERE gv.raw_grade IS NOT NULL
ON CONFLICT (school_id, grade, subject_match) DO NOTHING;


-- ---- SOUTHPREP (7368546879) — not in prod, no-ops --------------------------
INSERT INTO public.subject_overrides (school_id, grade, subject_match, subject_override, source)
SELECT s.school_id, gv.raw_grade, r.subject_match, r.subject_override, 'edvance_api'
FROM (VALUES
  ('Grade K','Mathematics','Math'),
  ('Grade 1','Mathematics','Math'),
  ('Grade 2','Mathematics','Math'),
  ('Grade K','Other','ELA'),
  ('Grade 1','Other','ELA'),
  ('Grade 2','Other','ELA')
) AS r(clean_grade, subject_match, subject_override)
CROSS JOIN LATERAL (VALUES
  (r.clean_grade),
  (CASE r.clean_grade
     WHEN 'Grade K' THEN '0 - Grade K' WHEN 'Grade 1' THEN '1 - Grade 1'
     WHEN 'Grade 2' THEN '2 - Grade 2' END)
) AS gv(raw_grade)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '7368546879') s
WHERE gv.raw_grade IS NOT NULL
ON CONFLICT (school_id, grade, subject_match) DO NOTHING;

-- Brightview (7448280461): SubjectOverrideConfigJson = [] → no subject_overrides.


-- =============================================================================
-- 2. subject_course_overrides  (CFP only — verbatim MapSubjectWithCourseNameJson)
--    Inserted LONGEST-pattern-first so first-match-by-override_id picks the most
--    specific course (e.g. "HS English II" before the "HS English I" substring).
--    Typos & spacing preserved EXACTLY (HS Alegra II / HS Honors Pre Calculas /
--    'HS Honors English II ' trailing space / 'HS Honors  English IV' double space).
-- =============================================================================
INSERT INTO public.subject_course_overrides (school_id, course_name_match_regex, subject_override, source)
SELECT s.school_id, v.rx, v.ovr, 'edvance_api'
FROM (VALUES
  ('HS United States Government','HS United States Government'),
  ('HS United States History','HS United States History'),
  ('HS Honors Pre Calculus','HS Honors Pre Calculas'),
  ('HS Honors English III','HS Honors English III'),
  ('HS Honors  English IV','HS Honors English IV'),
  ('HS Honors English II ','HS Honors English II'),
  ('HS Honors Algebra II','HS Honors Algebra II'),
  ('HS Honors English I','HS Honors English I'),
  ('HS Honors Algebra I','HS Honors Algebra I'),
  ('HS Honors Geometry','HS Honors Geometry'),
  ('HS Integrated Math','HS Integrated Math'),
  ('HS World History','HS World History'),
  ('HS English III','HS English III'),
  ('HS English IV','HS English IV'),
  ('HS English II','HS English II'),
  ('HS Algebra II','HS Algebra II'),
  ('HS Economics','HS Economics'),
  ('HS English I','HS English I'),
  ('HS Algebra I','HS Algebra I'),
  ('HS Geometry','HS Geometry'),
  ('HS Physics','HS Physics'),
  ('HS Biology','HS Biology')
) AS v(rx, ovr)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '554425139') s
-- DO UPDATE (not DO NOTHING) so re-seeding CONVERGES an already-seeded DB — e.g.
-- the 2026-07 'HS Alegra II'->'HS Algebra II' typo fix self-heals on reset.
ON CONFLICT (school_id, course_name_match_regex) DO UPDATE
  SET subject_override = EXCLUDED.subject_override;


-- =============================================================================
-- 3. school_grade_overrides  (school_id, grade_match[], grade_override)
--    One row per canonical OUTPUT grade listing every raw variant (prefixed + clean).
-- =============================================================================

-- ---- ATHENIAN (K-8) ----
INSERT INTO public.school_grade_overrides (school_id, grade_match, grade_override)
SELECT s.school_id, v.gm::text[], v.go
FROM (VALUES
  (ARRAY['0 - Grade K','Grade K'], 'Grade K'),
  (ARRAY['1 - Grade 1','Grade 1'], 'Grade 1'),
  (ARRAY['2 - Grade 2','Grade 2'], 'Grade 2'),
  (ARRAY['3 - Grade 3','Grade 3'], 'Grade 3'),
  (ARRAY['4 - Grade 4','Grade 4'], 'Grade 4'),
  (ARRAY['5 - Grade 5','Grade 5'], 'Grade 5'),
  (ARRAY['6 - Grade 6','Grade 6'], 'Grade 6'),
  (ARRAY['7 - Grade 7','Grade 7'], 'Grade 7'),
  (ARRAY['8 - Grade 8','Grade 8'], 'Grade 8')
) AS v(gm, go)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '186370968') s
ON CONFLICT (school_id, grade_override) DO NOTHING;

-- ---- CRESTWELL (K-8) ----
INSERT INTO public.school_grade_overrides (school_id, grade_match, grade_override)
SELECT s.school_id, v.gm::text[], v.go
FROM (VALUES
  (ARRAY['0 - Grade K','Grade K'], 'Grade K'),
  (ARRAY['1 - Grade 1','Grade 1'], 'Grade 1'),
  (ARRAY['2 - Grade 2','Grade 2'], 'Grade 2'),
  (ARRAY['3 - Grade 3','Grade 3'], 'Grade 3'),
  (ARRAY['4 - Grade 4','Grade 4'], 'Grade 4'),
  (ARRAY['5 - Grade 5','Grade 5'], 'Grade 5'),
  (ARRAY['6 - Grade 6','Grade 6'], 'Grade 6'),
  (ARRAY['7 - Grade 7','Grade 7'], 'Grade 7'),
  (ARRAY['8 - Grade 8','Grade 8'], 'Grade 8')
) AS v(gm, go)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '7440430446') s
ON CONFLICT (school_id, grade_override) DO NOTHING;

-- ---- CFP (K-8 + Higher-Ed passthrough + 9-12 → 'Regular 9–12' en-dash U+2013) ----
INSERT INTO public.school_grade_overrides (school_id, grade_match, grade_override)
SELECT s.school_id, v.gm::text[], v.go
FROM (VALUES
  (ARRAY['0 - Grade K','Grade K'], 'Grade K'),
  (ARRAY['1 - Grade 1','Grade 1'], 'Grade 1'),
  (ARRAY['2 - Grade 2','Grade 2'], 'Grade 2'),
  (ARRAY['3 - Grade 3','Grade 3'], 'Grade 3'),
  (ARRAY['4 - Grade 4','Grade 4'], 'Grade 4'),
  (ARRAY['5 - Grade 5','Grade 5'], 'Grade 5'),
  (ARRAY['6 - Grade 6','Grade 6'], 'Grade 6'),
  (ARRAY['7 - Grade 7','Grade 7'], 'Grade 7'),
  (ARRAY['8 - Grade 8','Grade 8'], 'Grade 8'),
  (ARRAY['9 - Grade 9','Grade 9','10 - Grade 10','Grade 10','11 - Grade 11','Grade 11','12 - Grade 12','Grade 12','Regular 9-12'], 'Regular 9–12'),
  (ARRAY['Higher-Ed','Higher Ed'], 'Higher-Ed')
) AS v(gm, go)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '554425139') s
-- DO UPDATE so re-seeding CONVERGES the grade_match arrays (else the 2026-07
-- folder band-name variants 'Higher Ed'/'Regular 9-12' never append on a seeded DB).
ON CONFLICT (school_id, grade_override) DO UPDATE
  SET grade_match = EXCLUDED.grade_match;

-- ---- SOUTHPREP (K-8) — not in prod, no-ops ----
INSERT INTO public.school_grade_overrides (school_id, grade_match, grade_override)
SELECT s.school_id, v.gm::text[], v.go
FROM (VALUES
  (ARRAY['0 - Grade K','Grade K'], 'Grade K'),
  (ARRAY['1 - Grade 1','Grade 1'], 'Grade 1'),
  (ARRAY['2 - Grade 2','Grade 2'], 'Grade 2'),
  (ARRAY['3 - Grade 3','Grade 3'], 'Grade 3'),
  (ARRAY['4 - Grade 4','Grade 4'], 'Grade 4'),
  (ARRAY['5 - Grade 5','Grade 5'], 'Grade 5'),
  (ARRAY['6 - Grade 6','Grade 6'], 'Grade 6'),
  (ARRAY['7 - Grade 7','Grade 7'], 'Grade 7'),
  (ARRAY['8 - Grade 8','Grade 8'], 'Grade 8')
) AS v(gm, go)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '7368546879') s
ON CONFLICT (school_id, grade_override) DO NOTHING;

-- ---- BRIGHTVIEW (K-8) — not in prod, no-ops ----
INSERT INTO public.school_grade_overrides (school_id, grade_match, grade_override)
SELECT s.school_id, v.gm::text[], v.go
FROM (VALUES
  (ARRAY['0 - Grade K','Grade K'], 'Grade K'),
  (ARRAY['1 - Grade 1','Grade 1'], 'Grade 1'),
  (ARRAY['2 - Grade 2','Grade 2'], 'Grade 2'),
  (ARRAY['3 - Grade 3','Grade 3'], 'Grade 3'),
  (ARRAY['4 - Grade 4','Grade 4'], 'Grade 4'),
  (ARRAY['5 - Grade 5','Grade 5'], 'Grade 5'),
  (ARRAY['6 - Grade 6','Grade 6'], 'Grade 6'),
  (ARRAY['7 - Grade 7','Grade 7'], 'Grade 7'),
  (ARRAY['8 - Grade 8','Grade 8'], 'Grade 8')
) AS v(gm, go)
CROSS JOIN (SELECT school_id FROM public.schools WHERE schoology_building_id = '7448280461') s
ON CONFLICT (school_id, grade_override) DO NOTHING;
