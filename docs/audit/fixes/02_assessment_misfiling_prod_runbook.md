# Assessment Misfiling Fixes — Production Runbook

**Read this before applying any of the misfiling / data-quality fixes to production.**
Self-contained: every SQL pattern needed is inline, so it works without the original
session scratchpad. Written 2026-07-09 after applying + verifying all of the below on
**local dev** (Athenian / CFP / Crestwell).

Related: [`../assessment_misfiling_audit.md`](../assessment_misfiling_audit.md),
[`../06_cubes_and_reports.md`](../06_cubes_and_reports.md), memory `project_assessment_misfiling_audit`.

---

## 0. What was fixed on local (and must be replayed on prod)

All changes were **direct, scoped SQL** — the ingestion pipeline was **never** re-run —
each backed up to a `*_bak` table and verified on the live dashboard.

| # | Fix | Count | Tables touched | Backup |
|---|---|---|---|---|
| 1 | **Relabel** (grade/subject wrong, no twin) | 9 + 2 | `dim_subject`, `fact_student_submission`, `cube_question_summary`, `cube_user_summary`, `dim_question_data` — update subject/grade **columns**, keep `subject_id` | `fix_bak_*`, `fix3_bak_*` |
| 2 | **Twin merge** (same test under 2 labels) | 17 + 1 | reassign `subject_id` A→B on `fact`, `dim_item`, `cube_question_summary`, `cube_question_summary_overall`, `cube_grade_summary`, `cube_school_summary`; fix subject/grade on `fact`/cubes/`cube_user_summary`/`dim_question_data`; `DELETE` A's `dim_subject` | `mrg_bak_*` |
| 3 | **Phantom ghost-card cleanup** (0-student cards) | 63 rows | `DELETE` empty `dim_subject` + their `dim_item` pairings | `clean_bak_*` |
| 4 | **dim_item heal** (repairs a side effect of #3) | 20 rows | restore `dim_item` rows #3 wrongly deleted that real assessments still need | INSERT-only |
| 5 | **Stale `dim_question_data` cleanup** | 18 | 9 delete duplicates + 9 relabel to authoritative label | `dqdclean_bak` |

**NOT applied anywhere (do NOT push to prod):** 7 items held for Fatima's confirmation;
36 `dim_item`-gap assessments (see §6); 2 skeptic-overturned; the needs-human
"2 Digit Addition" grade question.

---

## 1. Two data-model facts that drive everything

1. **`subject_id` = uuid_6 hash of `(school_id, subject, assessment_type, grade, session, item_name)`.**
   Section-agnostic but **assessment_type-specific**. Same test under two grades/subjects/types
   → two different `subject_id`s ("twins").
2. **`dim_item` PK = `(school_id, item_id)`** → **one item belongs to exactly one `subject_id`.**
   You **cannot** add a second `dim_item` row for the same item. This is why §6 gaps are hard.
3. The dashboard card's **Total Students** = `SUM over (item_id IN dim_item WHERE subject_id=B) of
   MAX(cube_school_summary.total_students)`. So **an incomplete `dim_item` under-counts the card**,
   even when `fact` is correct. After ANY merge you MUST re-check this (see §5 verify).

---

## 2. Golden rules (never skip on prod)

- ⛔ **Never re-run the ingestion pipeline on prod** — prod has **no raw/staging**; it would wipe data.
- ✅ Every change inside `BEGIN … COMMIT`, with a `*_bak` table created first.
- ✅ **Never hardcode local `subject_id`/`item_id`.** Prod IDs differ by data vintage. Always look
  them up on the target DB by business key `(school_id, subject, grade, session, assessment_type, item_name)`.
- ✅ `SET statement_timeout = 0;` at session start (prod default is 2 min; cube work exceeds it).
- ✅ Verify on the **live tenant-role backend** (Playwright/API), not just direct DB
  (direct/service-role DB bypasses RLS and can show data the app can't).
- ✅ Rotate the prod DB password when done. Keep `*_bak` tables until confident.
- Prod: Supabase `fkeazldazwzdkpwhngbm`, backend via `railway run --service backend …`.

---

## 3. Procedure

### Step 0 — Prep
1. Connect to prod. `SET statement_timeout = 0;`
2. Record baseline KPIs (Total Students per school) to prove nothing else moved later.

### Step 1 — Re-audit on prod (confirm, don't assume)
Prod is a different vintage. Re-run the standard-vs-label audit on prod and only fix what it
re-confirms. Core query (flag assessments whose questions' standards disagree with the label):

```sql
SELECT dqd.school_id, dqd.subject, dqd.grade, dqd.session, dqd.assessment_type, dqd.item_name,
       ds.grader AS std_grade, ds.subject AS std_subject, count(*) n
FROM dim_question_data dqd
LEFT JOIN dim_standard ds ON ds.identifier = dqd.identifier   -- 95% of questions resolve
GROUP BY 1,2,3,4,5,6,7,8;
```
Decode: `dim_standard.grader` already holds the grade ("Kindergarten","Grade 1".."Grade 8",
band "Grade 9-12"/"K-12" = can't pin a grade). Normalise subject families (Mathematics/B.E.S.T./
Algebra→Math; English/Reading→ELA; Science; Social Studies/History/Civics). **Corroborate every
flag** with the student cohort's dominant actual grade + the course (`dim_course` via `fact.course_nid`)
before trusting it — off-grade standards are legitimate (e.g. Grade-8 Algebra I uses MA.912.*; MJ US
History = Grade 7 but uses SS.8.A codes).

### Step 2 — Relabels (fix #1)
Per confirmed relabel, look up prod `subject_id` by key, then (grade stays if only subject changes):

```sql
BEGIN;
CREATE TABLE IF NOT EXISTS relbl_bak_dim_subject (LIKE dim_subject);
INSERT INTO relbl_bak_dim_subject SELECT * FROM dim_subject WHERE subject_id = :B;  -- (+ same for each table below)

UPDATE dim_subject            SET subject=:NS, grade=:NG WHERE subject_id = :B;
UPDATE fact_student_submission SET subject=:NS, grade=:NG WHERE subject_id = :B;
UPDATE cube_question_summary  SET subject=:NS, grade=:NG WHERE subject_id = :B;
UPDATE cube_user_summary      SET subject=:NS, grade=:NG
       WHERE school_id=:SCH AND item_id IN (SELECT item_id FROM dim_item WHERE subject_id=:B)
         AND session=:SES AND subject=:OS AND grade=:OG;
UPDATE dim_question_data      SET subject=:NS, grade=:NG
       WHERE school_id=:SCH AND item_id IN (SELECT item_id FROM dim_item WHERE subject_id=:B)
         AND session=:SES AND subject=:OS AND grade=:OG AND item_name=:ITEM;
COMMIT;
```
Keep the same `subject_id` (it is an opaque key; the dashboard reads subject/grade from the columns).

### Step 3 — Twin merges (fix #2)
Only merge when A and B share `(school, item_name, session, subject, grade)` at the CORRECT label
and **assessment_type MATCHES**. Look up A (misfile) and B (correct twin). Then:

```sql
BEGIN;
-- back up A+B rows of every table below to mrg_bak_* first, then:
UPDATE fact_student_submission SET subject_id=:B, subject=:NS, grade=:NG,
       grade_id=COALESCE((SELECT grade_id FROM dim_grade g WHERE g.school_id=:SCH AND g.grade=:NG LIMIT 1), grade_id)
       WHERE subject_id=:A;
UPDATE dim_item                     SET subject_id=:B WHERE subject_id=:A;
UPDATE cube_question_summary        SET subject_id=:B, subject=:NS, grade=:NG WHERE subject_id=:A;
UPDATE cube_question_summary_overall SET subject_id=:B WHERE subject_id=:A;
UPDATE cube_grade_summary           SET subject_id=:B WHERE subject_id=:A;
UPDATE cube_school_summary          SET subject_id=:B WHERE subject_id=:A;
UPDATE cube_user_summary  SET subject=:NS, grade=:NG
       WHERE school_id=:SCH AND item_id IN (:A_items) AND session=:SES AND subject=:OS AND grade=:OG AND assessment_type=:AT;
UPDATE dim_question_data  SET subject=:NS, grade=:NG
       WHERE school_id=:SCH AND item_id IN (:A_items) AND session=:SES AND subject=:OS AND grade=:OG;
DELETE FROM dim_subject WHERE subject_id=:A;
COMMIT;
```
Then run the **card==fact check** (§5). If B's card < distinct fact students, an item is missing from
`dim_item` (it was cross-filed under a phantom) — restore it (see §4 heal, same INSERT).

### Step 4 — Phantom cleanup + heal (do as ONE pair, in order)
Phantom = `dim_subject` with **0 fact AND 0 rows in every cube table**.

```sql
BEGIN;
-- 1. back up, then delete the ghost dim_subject + their dim_item pairings
CREATE TEMP TABLE ph AS
  SELECT ds.subject_id FROM dim_subject ds
  LEFT JOIN (SELECT subject_id,count(*) c FROM fact_student_submission GROUP BY 1) f USING(subject_id)
  WHERE COALESCE(f.c,0)=0;
-- (verify: these subject_ids also have 0 in cube_question_summary/_overall/grade/school)
CREATE TABLE IF NOT EXISTS clean_bak_dim_subject (LIKE dim_subject);
CREATE TABLE IF NOT EXISTS clean_bak_dim_item    (LIKE dim_item);
INSERT INTO clean_bak_dim_subject SELECT * FROM dim_subject WHERE subject_id IN (SELECT subject_id FROM ph);
INSERT INTO clean_bak_dim_item    SELECT * FROM dim_item    WHERE subject_id IN (SELECT subject_id FROM ph);
DELETE FROM dim_item    WHERE subject_id IN (SELECT subject_id FROM ph);
DELETE FROM dim_subject WHERE subject_id IN (SELECT subject_id FROM ph);

-- 2. HEAL immediately: any dim_item just deleted whose item is still needed by a REAL assessment
INSERT INTO dim_item (item_id, school_id, subject_id, item_type, item_name, school_id_csv,
                      section_name, section_instructors, assessment_date)
SELECT DISTINCT b.item_id, b.school_id, f.subject_id, b.item_type, b.item_name, b.school_id_csv,
       b.section_name, b.section_instructors, b.assessment_date
FROM clean_bak_dim_item b
JOIN fact_student_submission f ON f.item_id=b.item_id
JOIN dim_subject ds ON ds.subject_id=f.subject_id            -- f.subject_id is a REAL assessment
WHERE NOT EXISTS (SELECT 1 FROM dim_item d WHERE d.item_id=f.item_id AND d.subject_id=f.subject_id);
COMMIT;
```
**This heal is mandatory** — the naive cleanup deleted `dim_item` rows ~20 real tests needed, which
under-counted their cards until repaired. Do cleanup+heal together so no real test is ever left broken.

### Step 5 — Stale `dim_question_data` cleanup (fix #5)
Per stale wrong-label group: **delete** if a correct-label row already exists for the same item
(pure duplicate), else **relabel** to the authoritative `dim_subject` label. Back up to `dqdclean_bak`
first. Correct label = `dim_subject.subject/grade` of the fact-bearing `subject_id` for the item.

### Step 6 — Verification gate (the important part)
Run for **every** touched `subject_id`:

```sql
-- card (SUMX) must equal distinct fact headcount
SELECT
 (SELECT count(DISTINCT user_uid) FROM fact_student_submission WHERE subject_id = :B) AS fact_students,
 (SELECT COALESCE(SUM(ts),0) FROM (
    SELECT item_id, MAX(total_students) ts FROM cube_school_summary
    WHERE subject_id=:B AND item_id IN (SELECT item_id FROM dim_item WHERE subject_id=:B)
    GROUP BY item_id) t) AS card_students,
 (SELECT count(*) FROM dim_item WHERE subject_id=:B) AS dim_items;   -- must be > 0
```
Then: (a) **KPI conservation** — school Total Students match the Step-0 baseline except for intended
moves; (b) **live tenant-role sweep** — each fixed report shows correct grade/subject, combined
sections/teachers, `card==fact`, no duplicate cards; (c) spot-check vs the **legacy PDFs**.

### Step 7 — Close out
Rotate the prod DB password. Keep `*_bak` tables as rollback until fully confident.

---

## 6. Known-OPEN, deliberately NOT auto-fixed: 36 `dim_item`-gap assessments

29 fully **invisible** (fact+cubes exist but 0 `dim_item` → no card; ~474 students) + 7
**under-counting**. Split Athenian 25h/6u, CFP 3h, Crestwell 1h/1u. **All 36 have the CORRECT label**
(cohort=100% + course confirm) — it is purely a `dim_item` wiring problem, not a mislabel.

**Why they can't be bulk-fixed:** because `dim_item` PK = `(school_id, item_id)` and the same item is
**scattered across several `subject_id`s** by multi-export/re-export cross-filing (same grade/subject,
different assessment_type, sometimes even different `item_name` e.g. "Chapter 16.1" vs "Chapter 16 Part 1").
Categorised: 20 REASSIGN (owner is a metadata shadow), 14 MERGE-TYPE (same test split, both have
students → needs merge), 2 CONFLICT (grade dispute, tiny). Even "clean" reassigns cascade between
interconnected fragments. → needs careful **case-by-case merge**, likely with source/Fatima input.
Left as-is on local (pre-existing, mostly small weekly/benchmark tests). Do NOT sweep these blindly.
