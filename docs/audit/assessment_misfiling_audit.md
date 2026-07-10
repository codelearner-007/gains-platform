# Assessment Misfiling Audit — wrong subject / wrong grade

_Read-only scan of **all 1,919 assessments** across Athenian, CFP, and Crestwell (local dev DB, 2026-07-08). **No data was changed** — this is a candidate list for manual review._

## How each assessment was checked

An assessment's subject & grade come only from the **Schoology export folder**. Each was cross-checked against three folder-independent signals, then every flag was adversarially verified (12 AI verifiers querying the live DB):

1. **Standard codes (anchor)** — the grade/subject encoded in the standards the test's questions cover (e.g. `ELA.6.*` = ELA grade 6). Grade uses only single-grade codes; cross-cutting bands like `ELA.K12.*` are ignored.
2. **Student cohort** — the dominant grade of the students who took it (their own grade across all their other work).
3. **Duplicate title** — the same test filed under other grades/subjects in the same school+session.

Cases where standards are simply coded for another grade but the students & label agree (e.g. **Civics** taught in grade 8 using `SS.7` standards) were classified **legitimate, not misfiled**.

## Summary

- **Confirmed misfiles: 37** — Athenian 31 · Central 5 · Crestwell 1
  - Wrong **grade** only: 26
  - Wrong **subject** only: 3
  - Wrong **both**: 8
- Excluded as **legitimate**: 46 (35 off-grade standards e.g. Civics/History · 11 CFP dual-enrollment)

> Grade/subject shown as **Filed → Should be**. Confidence `medium` = inferred from the student cohort only (the item carries no standard codes). `subject_id` is one representative id (same test may span assessment-types).

## A. Confirmed misfiles — WRONG SUBJECT (content is a different subject)

| School | Assessment | Filed as | Should be | Conf | Why |
|---|---|---|---|---|---|
| Athenian | Inherited Traits 'Genius Challenge' | Algebra/Grade 8 | **Science / Grade 1** | high | All 18 takers' modal grade is Grade 1 and an identical-title twin is filed under Science/Grade 1; a genetics 'Genius Challenge' taken by Grade-1 stude |
| Athenian | Plant Needs 'Genius Challenge' | Algebra/Grade 8 | **Science / Grade 1** | high | All 18 takers' modal folder-grade is Grade 1, an identical-title twin exists under Science/Grade 1, and the item is a biology topic — an 'Algebra/Grad |
| Athenian | Chapter 16 | ELA/Grade 2 | **Math** | high | Standards are 100% MA.2.FR.1.1/1.2 (grade-2 Math fractions) with grade-2 students, so the folder subject ELA is wrong; grade (2) is correct and same t |
| Athenian | Chapter 18 | ELA/Grade 2 | **Math / Grade K** | high | Despite the generic reused title, this instance's standards are 100% MA.K.GR.* (Kindergarten Math geometry) and takers' modal grade is K, so the ELA/G |
| Athenian | Chapter 18 | ELA/Grade 3 | **Math / Grade 5** | high | Standards are 100% Math with ~87% MA.5.DP.* (grade 5, minor MA.4.DP), contradicting the ELA/Grade 3 folder on both subject and grade; folder-independe |
| Athenian | Chapter 2 | ELA/Grade 3 | **Math / Grade 1** | high | Standards are 100% MA.1.NSO.* (Math, grade 1) — a folder-independent anchor that contradicts the ELA/Grade 3 folder on both dimensions; generic 'Chapt |
| Athenian | Module 8 Test | ELA/Grade 7 | **Math** | high | Standards are 100% Math (MA.7.AR.2.1 x540, MA.8.AR.2.2 x30) with grade-7 students, so folder subject ELA is wrong; grade 7 correct and the title twins |
| Athenian | Unit 3 Test | ELA/Grade 7 | **Social Studies** | high | Standards are 100% SS.8.A.* US History (Social Studies) so folder ELA is clearly wrong, but all 31 takers form a clean Grade-7 slate matching the fold |
| Central | Unit 7 Benchmark Test: Working With Electricit | ELA/Grade 1 | **Science / Grade 5** | high | Standards are 100% SCI.5.* (Science, grade 5) and the title is Science content, so the ELA/Grade-1 folder is wrong on both fields -> Grade 5 / Science |
| Central | Unit 8 Test: Forces and Motion | ELA/Grade 3 | **Science / Grade 2** | high | Standards are 100% SCI.2.* (Science, grade 2) and 'Forces and Motion' is Science, so folder ELA/Grade 3 is wrong on both -> Grade 2 / Science. |
| Central | Unit 8 Test: Classifying Plants and Animals | ELA/Grade 4 | **Science / Grade 3** | high | Standards are 100% SCI.3.L.15.* (life Science, grade 3) and the title is Science, so folder ELA/Grade 4 is wrong on both -> Grade 3 / Science. |

## B. Confirmed misfiles — WRONG GRADE (subject correct)

| School | Assessment | Filed grade | Should be | Conf | Why |
|---|---|---|---|---|---|
| Athenian | Happy Healthy Me: Weekly Assessment: Week 1 | ELA/Grade 1 | **Grade K** | high | Standards are 100% ELA.K.* (Kindergarten codes) and identical-title twins sit under ELA/Grade K; the Grade-1 folder is a grade misfile with subject EL |
| Athenian | Happy Healthy Me: Weekly Assessment: Week 3 | ELA/Grade 1 | **Grade K** | high | Standards are 100% ELA.K.* (folder-independent Kindergarten foundational-reading codes) and three identical-title twins are all filed under ELA/Grade  |
| Athenian | CW-Cold Read: Roberto Clemente | ELA/Grade 2 | **Grade 3** | high | Standards are entirely LA.3.LAFS.3.* (grade-3 reading, folder-independent anchor) and takers' modal grade is Grade 3; the Grade-2 folder is a grade mi |
| Athenian | M4W2  Vocabulary Quiz | ELA/Grade 2 | **Grade 3** | high | No standard codes, but all 19 takers' modal grade across all their folders is Grade 3 and an ELA/Grade 3 twin of the same title exists; the Grade-2 fo |
| Athenian | 12/5 Reading Classwork | ELA/Grade 3 | **Grade 4** | high | No standards, but all 19 takers are unanimously Grade 4 across their OTHER same-session (2024-25) assessment folders and a twin title exists under Gra |
| Athenian | 12/9 Reading Classwork | ELA/Grade 3 | **Grade 4** | high | No standards, but all 18 takers are unanimously Grade 4 across their OTHER same-session (2024-25) assessments and a twin title exists under Grade 4, s |
| Athenian | Meet in the Middle: Weekly Assessment: Week 1 | ELA/Grade 3 | **Grade 2** | high | Standards are 100% ELA.2.* (ELA, grade 2): subject ELA is correct but the single-grade codes anchor Grade 2, contradicting the Grade 3 folder; takers  |
| Athenian | M4W2 Vocabulary Quiz | ELA/Grade 4 | **Grade 5** | high | No standards, but all 18 takers are unanimously Grade 5 across their OTHER same-session (2024-25) assessments and a twin exists under Grade 5, so the  |
| Athenian | Module 8 Week 1 Vocabulary Quiz | ELA/Grade 4 | **Grade 2** | high | No standards, but all 20 takers are unanimously Grade 2 across their OTHER same-session (2025-26) assessments and a twin exists under Grade 2, so the  |
| Athenian | Through an Animal's Eyes Unit Test | ELA/Grade 8 | **Grade 6** | high | Standards are 100% ELA.6.* (grade-6 single-grade codes), all 39 takers are dominant Grade 6, and the same title is also filed under Grade 6 -- folder  |
| Athenian | Adding and Subtracting Money - 12/16/24 | Math/Grade 2 | **Grade 3** | high | No standards, but the exact date-stamped twin 'Adding and Subtracting Money - 12/16/24' is filed under Grade 3 (Sec 1/2) while this Sec-3 copy sits un |
| Athenian | 12/04 8.4 Homework | Math/Grade 3 | **Grade 4** | medium | No standards, but all 22 takers register overwhelmingly as Grade 4 across 60+ of their other assessments with essentially no other Grade-3 presence; f |
| Athenian | 12/05 8.4 Homework | Math/Grade 3 | **Grade 4** | high | No standards, but the exact date-stamped twin '12/05 8.4 Homework' is filed under Grade 4 (Sec 1), the 21 takers are per-student dominant Grade 4, and |
| Athenian | 12/09 8.6 Homework | Math/Grade 3 | **Grade 4** | high | No standards, but the exact date-stamped twin '12/09 8.6 Homework' is filed under Grade 4 (Sec 1), the 19 takers are per-student dominant Grade 4, and |
| Athenian | HW 12/10 Spiral Review | Math/Grade 5 | **Grade 7** | high | Course is 'MJ Mathematics 2' (Florida M/J Math 2 = grade 7) but filed under Grade 5 — same pattern as the confirmed HW 12/4 / HW 12/6 Grade-5→7 misfil |
| Athenian | HW 12/3 8.1 | Math/Grade 5 | **Grade 6** | medium | No standard codes, but all 30 takers carry a complete Grade 6 slate in-session (Grade 6 ELA/History/Science/Math); only this misfiled Math-homework ba |
| Athenian | HW 12/4 7.2 - 7.3 | Math/Grade 5 | **Grade 7** | high | Standards are 100% MA.7.* (grade-7 single-grade codes) and all 28 takers are dominant Grade 7 -- folder Grade 5 is a genuine grade misfile; subject (M |
| Athenian | HW 12/4 8.2 | Math/Grade 5 | **Grade 6** | high | Standards are 100% MA.6.* (grade-6 single-grade codes) and all 31 takers are dominant Grade 6 -- folder Grade 5 is a genuine grade misfile; subject (M |
| Athenian | HW 12/6 | Math/Grade 5 | **Grade 7** | high | Standards are ~97% MA.7.* (only a small MA.8.AR.1.3 tail) and all 28 takers are dominant Grade 7 -- folder Grade 5 is a genuine grade misfile; subject |
| Athenian | HW 12/9 Spiral Review | Math/Grade 5 | **Grade 7** | high | Course is 'MJ Mathematics 2' (Florida M/J Math 2 = grade 7) but filed under Grade 5 — same pattern as the confirmed HW 12/4 / HW 12/6 Grade-5→7 misfil |
| Athenian | Classwork End of Year Test | Math/Grade 6 | **Grade 1** | high | No standards, but all 17 takers register as Grade 1 across 100+ of their other assessments and the identical title has a legit Grade-1 Math twin (5e80 |
| Athenian | Science CW FSSA book matter #1 | Science/Grade 4 | **Grade 5** | medium | Twin of #2: no standards but all 38 takers appear in Grade 5 ELA+Math+Science and content is grade-5 FSSA 'matter' prep, so folder Grade 4 is a grade  |
| Athenian | science CW FSSA book  matter #2 | Science/Grade 4 | **Grade 5** | medium | No standards, but all 20 takers appear in Grade 5 ELA+Math+Science and the item is FSSA 'matter' prep (Florida science is state-tested in grade 5), so |
| Central | Home Sweet Habitat: Weekly Assessment: Week 1 | ELA/Grade 3 | **Grade 2** | high | Codes are ELA.2.*/LA.2.* (grade-2 ELA), takers 100% Grade 2, and a Grade-2 twin of the title exists; subject correct, grade folder wrong -> Grade 2. |
| Central | Home Sweet Habitat: Weekly Assessment: Week 3 | ELA/Grade 3 | **Grade 2** | high | Single-grade codes are all ELA.2.* (grade-2 ELA) with only ELA.K12 cross-cutting bands otherwise, and all 40 takers are Grade 2; subject ELA correct,  |
| Crestwell | Chapter 1 Test: Counting and Number Sense | Math/Grade 2 | **Grade 1** | high | Standards are 100% Grade-1 number-sense (MA.1.NSO.1.1/2.3), takers are dominantly Grade 1, and three same-named 'Chapter 1 Test: Counting and Number S |

## Caveats for manual verification

- **Student-grade signal is folder-derived** (a student's grade = the majority of their own assessment folders). It's robust in aggregate but, if a whole section were systematically misfiled, it could agree with a wrong folder — the standard-code anchor guards against this, but the few `medium` rows (no standards on the item) rest on the cohort signal alone.
- **Generic names** (`Chapter 18`, `Unit 3 Test`, `HW 12/4`) are reused across grades; each flagged instance was judged by *its own* standards/students, not the name.
- The corrected grade/subject is the **most-likely** value from the evidence; confirm against the source Schoology export before any remediation.

## Excluded as legitimate (for transparency)

- **Off-grade standards (35)** — label is correct, standards just coded for another grade. Dominated by **Civics/Grade 8** (15, `SS.7` standards) and **History/Grade 7** (10). Not misfiled.
- **CFP dual-enrollment (11)** — HS English III/IV under `Regular 9–12` vs `Higher-Ed`. Ambiguous HS/dual-enrollment grouping; **confirm with CFP** but treated as legitimate, not misfiled.

## Files

- `assessment_misfiling.csv` — all 81 candidates with verdicts, evidence, and reasoning (filter `verdict = GENUINE_MISFILE` for the actionable 35).
