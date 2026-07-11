-- =============================================================================
-- item_label_overrides seed — per-assessment misfiling corrections (durable).
-- Applied at staging (stg_student_submission.sql / stg_question_data.sql) as the
-- highest-precedence subject/grade override. See migration
-- 20260711120000_item_label_overrides.sql for the WHY.
--
-- Class A (48 rows): prior misfiling relabels PRESERVED — target labels are the
--   corrected values that already lived in fact/dims before the 2026-07 rebuild
--   (verified: fact label != staging label; not among the new-misfile set).
-- Class B (11 rows): NEW misfiles from the 2026-07 audit (STI-1), target labels
--   triangulated from section peers + mapped standards + taker home-grade.
--   The Crestwell "Chapter 1 Test" (item 7841245375) is intentionally HELD
--   pending grade confirmation (decision gate DG-3) and is NOT seeded here.
--
-- Idempotent: ON CONFLICT (school_id,item_id) DO UPDATE.
-- =============================================================================

INSERT INTO item_label_overrides
  (school_id, item_id, subject_override, grade_override, assessment_type_override, item_name_override, reason, source)
VALUES
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7615828993', 'Math', 'Grade 4', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- 12/04 8.4 Homework
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7615829935', 'Math', 'Grade 4', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- 12/05 8.4 Homework
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7624644120', 'Math', 'Grade 4', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- 12/09 8.6 Homework
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7613842590', 'ELA', 'Grade 4', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- 12/5 Reading Classwork
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7625528258', 'ELA', 'Grade 4', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- 12/9 Reading Classwork
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7637896011', 'Math', 'Grade 3', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Adding and Subtracting Money - 12/16/24
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7687663925', 'Math', 'Grade 2', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Chapter 16
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7687678128', 'Math', 'Grade 2', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Chapter 16
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7789640645', 'Math', 'Grade 4', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Chapter 16 Temperature and Time
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7702555934', 'Math', 'Grade 5', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Chapter 18
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7702561239', 'Math', 'Grade K', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Chapter 18
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7893373621', 'Math', 'Grade 1', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Chapter 2
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7708642601', 'Algebra', 'Grade 8', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Chapter 6 Test
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '8359960427', 'Algebra', 'Grade 8', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Chapter 9 Test
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '8346484076', 'Math', 'Grade 1', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Classwork End of Year Test
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7623891071', 'ELA', 'Grade 3', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- CW-Cold Read: Roberto Clemente
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7617762025', 'Math', 'Grade 6', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- HW 12/3 8.1
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7619625033', 'Math', 'Grade 7', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- HW 12/4 7.2 - 7.3
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7619615379', 'Math', 'Grade 6', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- HW 12/4 8.2
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7623314096', 'Math', 'Grade 7', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- HW 12/6
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7598715892', 'ELA', 'Grade 5', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- M4W2 Vocabulary Quiz
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7620225345', 'ELA', 'Grade 3', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- M4W2  Vocabulary Quiz
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7789287431', 'ELA', 'Grade 3', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- M7W2 Vocabulary Quiz
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7334679341', 'ELA', 'Grade 2', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Meet in the Middle: Weekly Assessment: Week 1
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7338206131', 'Math', 'Grade 7', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Module 8 Test
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '8336110460', 'ELA', 'Grade 2', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Module 8 Week 1 Vocabulary Quiz
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7334633943', 'ELA', 'Grade 1', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Now You See It, Now You Don''t: Weekly Assessment: Week 2
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7625255317', 'Science', 'Grade 5', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Science CW FSSA book matter #1
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7625334305', 'Science', 'Grade 5', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Science CW FSSA book matter #1
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7628056550', 'Science', 'Grade 5', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- science CW FSSA book  matter #2
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7696812668', 'Science', 'Grade 1', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Unit 3 Lesson 3 Quiz
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7701493741', 'Science', 'Grade 1', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Unit 3 Lesson 3 Quiz
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7338320727', 'History', 'Grade 7', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Unit 3 Test
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7338033968', 'Civics', 'Grade 8', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Unit 5 Test
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7338399404', 'Science', 'Grade 3', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Unit 7 Benchmark Test: Plants and the Environment
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7806926683', 'ELA', 'Grade 2', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Home Sweet Habitat: Weekly Assessment: Week 1
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7816901887', 'ELA', 'Grade 2', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Home Sweet Habitat: Weekly Assessment: Week 3
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7780237817', 'ELA', 'Grade 2', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Home Sweet Habitat: Weekly Assessment: Week 3
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7823076023', 'ELA', 'Grade 2', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Home Sweet Habitat: Weekly Assessment: Week 3
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7961339860', 'Science', 'Grade 7', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Living Things in the Biosphere
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '8216302399', 'HS Honors Algebra I', 'Higher-Ed', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Topic 3 Assessment A
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7891846801', 'Science', 'Grade 5', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Unit 7 Benchmark Test: Working With Electricity
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7997342490', 'Science', 'Grade 5', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Unit 7 Benchmark Test: Working With Electricity
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7891794271', 'Science', 'Grade 3', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Unit 8 Test: Classifying Plants and Animals
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7891742813', 'Science', 'Grade 2', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Unit 8 Test: Forces and Motion
  ((SELECT school_id FROM schools WHERE name='Crestwell School'), '8358079682', 'Math', 'Grade 2', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Chapter 16 Test: Fraction Concepts
  ((SELECT school_id FROM schools WHERE name='Crestwell School'), '7935427775', 'Math', 'Grade 3', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Chapter 17 Test: Classify Two-Dimensional Quadrilaterals and Identify Line Symmetry
  ((SELECT school_id FROM schools WHERE name='Crestwell School'), '8235331733', 'Reading', 'Grade 3', NULL, NULL, 'prior misfiling relabel preserved (2026-07 audit)', 'audit-2026-07'),  -- Make a Difference: Weekly Assessment: Week 2  -- ── Class B: new misfiles (2026-07 audit STI-1) ──────────────────────────
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7616266129', 'Science', 'Grade 1', NULL, NULL, 'STI-1 new misfile: Inherited Traits Genius Challenge, Sedlak Grade-1 Science section (filed Algebra/Grade 8)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7626085761', 'Science', 'Grade 1', NULL, NULL, 'STI-1 new misfile: Plant Needs Genius Challenge, Sedlak Grade-1 Science section (filed Algebra/Grade 8)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7337899755', 'ELA', 'Grade K', NULL, NULL, 'STI-1 new misfile: Happy Healthy Me Wk1, Watkins Grade-K ELA section, 100% ELA.K standards (filed Grade 1)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7337899774', 'ELA', 'Grade K', NULL, NULL, 'STI-1 new misfile: Happy Healthy Me Wk3, Watkins Grade-K ELA section, 100% ELA.K standards (filed Grade 1)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7626433775', 'Math', 'Grade 6', NULL, NULL, 'STI-1 new misfile: HW 12/9 Spiral Review, Burney Grade-6 section, MA.6 standards (filed Grade 5)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7628347421', 'Math', 'Grade 6', NULL, NULL, 'STI-1 new misfile: HW 12/10 Spiral Review, Burney Grade-6 section, MA.6 standards (filed Grade 5)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7626416439', 'Math', 'Grade 7', NULL, NULL, 'STI-1 new misfile: HW 12/9 Spiral Review, Burney Grade-7 section, MA.7 standards (filed Grade 5)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7628391502', 'Math', 'Grade 7', NULL, NULL, 'STI-1 new misfile: HW 12/10 Spiral Review, Burney Grade-7 section, MA.7 standards (filed Grade 5)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7892346412', 'ELA', 'Grade 6', NULL, NULL, 'STI-1 new misfile: Through an Animal''s Eyes Unit Test, Swidarski Grade-6 ELA section, 100% ELA.6 standards (filed Grade 8)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7964065626', 'Algebra', 'Grade 8', NULL, NULL, 'STI-1 new misfile: Topic 1, MS PRE ALG section, 100% MA.8 standards, siblings Topics 2-7 are Algebra/Grade 8 (filed Math/Grade 7)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '7964067882', 'Algebra', 'Grade 8', NULL, NULL, 'STI-1 new misfile: Topic 1, MS PRE ALG section, 100% MA.8 standards, siblings Topics 2-7 are Algebra/Grade 8 (filed Math/Grade 7)', 'audit-2026-07')
ON CONFLICT (school_id, item_id) DO UPDATE
  SET subject_override         = EXCLUDED.subject_override,
      grade_override           = EXCLUDED.grade_override,
      assessment_type_override = EXCLUDED.assessment_type_override,
      item_name_override       = EXCLUDED.item_name_override,
      reason                   = EXCLUDED.reason,
      source                   = EXCLUDED.source;
