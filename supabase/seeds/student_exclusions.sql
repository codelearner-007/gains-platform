-- =============================================================================
-- student_exclusions seed — confirmed internal STAFF/DEMO test accounts to drop
-- at ingest. See migration 20260712120000_student_exclusions.sql.
--
-- 2026-07 audit (owner-confirmed): Crestwell has 5 internal staff/sandbox test
-- accounts (adult names, "Sec 1"/"Sec 2" sandbox sections) whose ONLY activity is
-- clicking through "Chapter 1/2/3 Test: Counting and Number Sense" (Grade-1 math)
-- sandbox items. They have zero real-student data. Dropping them also removes
-- the 5 phantom sandbox assessment cards (items 7610639442/551, 7841245375,
-- 7610639443/444) which had no real students.
-- =============================================================================

INSERT INTO student_exclusions (school_id, user_uid, reason, source)
VALUES
  ((SELECT school_id FROM schools WHERE name='Crestwell School'), '136696902', 'internal demo/staff account (Ahmed Shamsheer); sandbox Chapter-Test data only', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Crestwell School'), '136697026', 'internal demo/staff account (Misbah Shaikh); sandbox Chapter-Test data only', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Crestwell School'), '136696876', 'internal demo/staff account (Palwasha Brohi); sandbox Chapter-Test data only', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Crestwell School'), '136696884', 'internal demo/staff account (Pareesa Brohi); sandbox Chapter-Test data only', 'audit-2026-07'),
  ((SELECT school_id FROM schools WHERE name='Crestwell School'), '136696874', 'internal demo/staff account (Sitara Shams); sandbox Chapter-Test data only', 'audit-2026-07')
ON CONFLICT (school_id, user_uid) DO NOTHING;
