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
  ((SELECT school_id FROM schools WHERE name='Central Florida Preparatory School'), '8200948758', 'ELA', 'Regular 9–12', 'spurious HS-ENG folder duplicate of Grade-2 Math test (43/45 student overlap, same section_nid)', 'audit-2026-07')
ON CONFLICT (school_id, item_id, subject, grade) DO NOTHING;
