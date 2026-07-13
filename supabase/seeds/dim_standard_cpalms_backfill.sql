-- =============================================================================
-- dim_standard CPALMS description backfill (2026-07 audit, F-E2/F-E3).
-- RUN AFTER load_standards.py + dim_standard_cleanup.sql. Idempotent.
--
-- 11 referenced-in-reports codes had no dim_standard row or a blank description.
-- Descriptions verified against CPALMS (cpalms.org) per code; retired framework
-- codes (LAFS/MACC/LA-2007) are annotated with their current B.E.S.T. successor.
-- =============================================================================

UPDATE dim_standard SET description='Demonstrate command of the conventions of standard English capitalization, punctuation, and spelling when writing (grade 5). [Retired LAFS.5.L.1.2; current B.E.S.T. successor ELA.5.C.3.1]' WHERE schoology_standard='ELA.5.L.1.2.m' AND (description IS NULL OR btrim(description)='');
UPDATE dim_standard SET description='Use sentence-level context as a clue to the meaning of a word or phrase (grade 3 vocabulary acquisition). [Retired LAFS.3.L.3.4.a]' WHERE schoology_standard='LA.3.LAFS.3.L.3.4.a' AND (description IS NULL OR btrim(description)='');
UPDATE dim_standard SET description='Compare and order objects indirectly or directly using measurable attributes such as length, height, and weight (Kindergarten). [Retired NGSSS MA.K.G.3.1]' WHERE schoology_standard='MA.K.3.1' AND (description IS NULL OR btrim(description)='');
UPDATE dim_standard SET description='Use research and inquiry skills to analyze American History using primary and secondary sources (reporting category / parent benchmark, grade 8).' WHERE schoology_standard='SOC.8.SS.8.A.1' AND (description IS NULL OR btrim(description)='');
UPDATE dim_standard SET description='Apply the rights and principles contained in the Constitution and Bill of Rights to the lives of citizens today (grade 8 Civics).' WHERE schoology_standard='SOC.8.SS.8.C.1.5' AND (description IS NULL OR btrim(description)='');

INSERT INTO dim_standard (uniques_id, identifier, schoology_standard, standard_new, strand, subject, description, cpalms_standard) VALUES
 (gen_random_uuid(),'ELA.6.RL.6.4.2','ELA.6.RL.6.4.2','2','Reading: Craft and Structure','English Language Arts','Determine the meaning of words and phrases as they are used in a text, including figurative and connotative meanings; analyze the impact of a specific word choice on meaning and tone (grade 6). [Retired LAFS.6.RL.2.4 / CCSS RL.6.4; B.E.S.T. successor ELA.6.V.1.3 & ELA.6.R.3.1]','ELA.6.V.1.3'),
 (gen_random_uuid(),'ELA.6.V.3.4','ELA.6.V.3.4','4','Language: Vocabulary Acquisition and Use','English Language Arts','Determine or clarify the meaning of unknown and multiple-meaning words and phrases based on grade 6 reading and content, choosing flexibly from a range of strategies (context clues, Greek/Latin roots and affixes, reference materials). [Retired LAFS.6.L.3.4; B.E.S.T. successor ELA.6.V.1.2 & ELA.6.V.1.3]','ELA.6.V.1.2'),
 (gen_random_uuid(),'LA.2.LA.2.1.6.3','LA.2.LA.2.1.6.3','3','Reading Process: Vocabulary Development','English Language Arts','The student will use context clues to determine meanings of unfamiliar words (grade 2). [Retired 2007 SSS LA.2.1.6.3; B.E.S.T. successor ELA.2.V.1.3]','ELA.2.V.1.3'),
 (gen_random_uuid(),'LA.2.LA.2.1.7.4','LA.2.LA.2.1.7.4','4','Reading Process: Reading Comprehension','English Language Arts','The student will identify cause-and-effect relationships in text (grade 2). [Retired 2007 NGSSS LA.2.1.7.4; B.E.S.T. successor ELA.3.R.2.1]','ELA.3.R.2.1'),
 (gen_random_uuid(),'MA.5.MACC.5.NBT.1.3.b','MA.5.MACC.5.NBT.1.3.b','b','Number and Operations in Base Ten','Math','Compare two decimals to thousandths based on meanings of the digits in each place, using >, =, and < symbols to record the results of comparisons (grade 5). [Retired MACC/MAFS.5.NBT.1.3.b; B.E.S.T. successor MA.5.NSO.1.4]','MA.5.NSO.1.4'),
 (gen_random_uuid(),'SOC.H.PreK-K.1','SOC.H.PreK-K.1','1','American History: Historical Inquiry and Analysis','Social Studies','Historical Inquiry and Analysis for the PreK-Kindergarten band (e.g., develop an understanding of how to use and create a timeline; SS.K.A.1.1). [current NGSSS SS.K.A.1]','SS.K.A.1')
ON CONFLICT DO NOTHING;
