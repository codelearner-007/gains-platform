-- =============================================================================
-- fact_row_exclusions seed — spurious per-(item, label) duplicate exports to drop
-- at the fact build. See migration 20260711130000_fact_row_exclusions.sql.
--
-- 2026-07 audit: 3 CFP "Chapter 8 Test: More 2-Digit Subtraction" (Grade-2 Math)
-- items were re-exported into a HS English folder (ELA / Regular 9–12) carrying a
-- partial-question duplicate of the same Grade-2 students (43/45 overlap with the
-- real Math rows, SAME section_nid). They render a phantom ELA/Regular 9–12 card.
-- A prior manual fix deleted them; this makes that durable. Grade-2 Math items
-- have no legitimate Regular 9–12 rows, so the (ELA, Regular 9–12) label is safe
-- to drop.
-- =============================================================================

INSERT INTO fact_row_exclusions (school_id, item_id, subject, grade, reason, source)
VALUES
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '8180432402', 'ELA', 'Regular 9–12', 'spurious HS-ENG folder duplicate of Grade-2 Math test (43/45 student overlap, same section_nid)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '8200948721', 'ELA', 'Regular 9–12', 'spurious HS-ENG folder duplicate of Grade-2 Math test (43/45 student overlap, same section_nid)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '8200948758', 'ELA', 'Regular 9–12', 'spurious HS-ENG folder duplicate of Grade-2 Math test (43/45 student overlap, same section_nid)', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '8362776921', 'HS Algebra I', 'Higher-Ed', 'Topic 8 cross-band remnant: Algebra test fragment mis-filed in a US History section (1 student, 33 rows)', 'audit-2026-07'),
  -- Athenian "HW Spiral Review" homework (2024-25). Customer (Fatima) confirmed
  -- these should NOT appear in assessment reporting under any grade: they are
  -- homework/spiral-review spanning Grade 6 AND Grade 7 (no single true grade).
  -- item_label_overrides relabels each item_id to its section grade (Math G6/G7);
  -- these exclusions then drop them at the fact build. Source rows retained in
  -- backups.hw_spiral_archive_20260713 (customer asked to keep the data, no hard delete).
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7626416439', 'Math', 'Grade 7', 'HW 12/9 Spiral Review homework, spans G6+G7 — customer: exclude from reporting (data archived)', 'fatima-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7626433775', 'Math', 'Grade 6', 'HW 12/9 Spiral Review homework, spans G6+G7 — customer: exclude from reporting (data archived)', 'fatima-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7628391502', 'Math', 'Grade 7', 'HW 12/10 Spiral Review homework, spans G6+G7 — customer: exclude from reporting (data archived)', 'fatima-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Athenian Academy of Technology and the Arts'), '7628347421', 'Math', 'Grade 6', 'HW 12/10 Spiral Review homework, spans G6+G7 — customer: exclude from reporting (data archived)', 'fatima-2026-07')
ON CONFLICT (school_id, item_id, subject, grade) DO NOTHING;
