-- cube_user_summary — per-(section, session, grade, subject, assessment_type,
-- user, item, question, standard, school) totals across many aggregate axes.
-- Notebook lines 2278-2483 (40_schoology_py_spec.md §7).
--
-- 6 chained intermediate aggregates, then a final SELECT that joins them all
-- onto the base grain.

-- Scoped rebuild: this cube embeds session-wide aggregate columns
-- (*_by_overall_year, *_by_section, *_by_standard, ...), so a per-subject scope
-- would leave sibling items' session-level columns stale. Instead we delete and
-- recompute the whole (school_id, session) slice from the PRESERVED fact. Empty
-- scope (full rebuild) falls through to TRUNCATE — byte-identical to legacy.
DO $scope$ BEGIN
  IF EXISTS (SELECT 1 FROM _scope_assessments) THEN
    DELETE FROM cube_user_summary
    WHERE (school_id, COALESCE(session, '(null)'))
          IN (SELECT school_id, COALESCE(session, '(null)') FROM _scope_assessments);
  ELSE
    TRUNCATE TABLE cube_user_summary;
  END IF;
END $scope$;

INSERT INTO cube_user_summary (
  id, school_id, school_id_csv, section_nid, section_instructors,
  session, grade, subject, assessment_type,
  user_uid, user_name, item_id, item_name, question_id, question_no, standards,
  total_possible_point, total_score,
  total_possible_point_by_question, total_score_by_question,
  total_possible_point_by_overall, total_score_by_overall,
  total_possible_point_by_overall_year, total_score_by_overall_year,
  total_possible_point_by_item, total_score_by_item,
  total_possible_point_by_section, total_score_by_section,
  total_possible_point_by_standard, total_score_by_standard,
  count_student, user_possible_point, user_overall_possible_point,
  student_name_hash, teacher_name_hash
)
WITH fact_join_qd AS (
  -- Bring (Question_No, Standards_ques, Total_Points) from dim_question_data.
  -- Total_Points is a TEXT column; cast to numeric for sums (NULL on cast fail).
  -- Notebook 2280: rename Standards->Standards_ques to disambiguate from
  -- Standards (we just keep it as `standards` here).
  SELECT
    f.school_id,
    f.school_id_csv,
    f.section_nid,
    f.section,
    f.user_uid,
    f.user_name,
    f.item_id,
    f.item_name,
    f.question_id,
    f.session,
    f.grade,
    f.subject,
    f.subject_id,
    f.assessment_type,
    f.points_possible,
    f.points_received,
    qd.question_no,
    -- standards_ques -> standards. NULL/'null'/blank -> 'Other' (notebook §8).
    CASE
      WHEN qd.standards IS NULL OR qd.standards IN ('', 'null') THEN 'Other'
      ELSE qd.standards
    END                                                AS standards,
    -- Cast Total_Points text to numeric for sum aggregations.
    NULLIF(qd.total_points, '')::numeric               AS total_points_num
  FROM fact_student_submission f
  LEFT JOIN (
    SELECT DISTINCT ON (school_id, question_id, position_number)
      school_id, question_id, position_number, question_no, standards, total_points
    FROM dim_question_data
    WHERE question_id IS NOT NULL
    ORDER BY school_id, question_id, position_number, standards NULLS LAST
  ) qd
    ON qd.school_id   = f.school_id
   AND qd.question_id = f.question_id
   AND COALESCE(qd.position_number, '__NULL__')
       = COALESCE(f.position_number, '__NULL__')
  -- Scoped rebuild: restrict the fact scan to the touched (school_id, session)
  -- slices so every downstream aggregate recomputes the whole slice from the
  -- preserved fact. No-op when _scope_assessments is empty (full rebuild).
  WHERE (NOT EXISTS (SELECT 1 FROM _scope_assessments)
         OR (f.school_id, COALESCE(f.session, '(null)'))
            IN (SELECT school_id, COALESCE(session, '(null)') FROM _scope_assessments))
),
section_meta AS (
  -- For each (school_id, section_nid) -> section_instructors.
  SELECT school_id, section_nid, section_instructors
  FROM dim_section
),
-- Step 1: Cube_User_Question_Summary per (Section_NID, Section_Instructors,
-- Session, Grade, Subject, Assessment_type, User_UID, User_Name, Item_ID,
-- Item_Name, School_ID).
-- Max_Total_Possible_Point_By_Question = round(sum(Total_Points), 2)
-- Total_Score_By_Question                = round(sum(Points_Received), 2)
user_question AS (
  SELECT
    f.school_id,
    f.section_nid,
    sm.section_instructors,
    f.session, f.grade, f.subject, f.assessment_type,
    f.user_uid, f.user_name,
    f.item_id, f.item_name,
    ROUND(SUM(f.total_points_num), 2)            AS max_total_possible_point_by_question,
    ROUND(SUM(f.points_received), 2)             AS total_score_by_question
  FROM fact_join_qd f
  LEFT JOIN section_meta sm
    ON sm.school_id   = f.school_id
   AND sm.section_nid = f.section_nid
  GROUP BY f.school_id, f.section_nid, sm.section_instructors,
           f.session, f.grade, f.subject, f.assessment_type,
           f.user_uid, f.user_name, f.item_id, f.item_name
),
-- Step 2: max_values = MAX(Max_Total_Possible_Point_By_Question) per
-- (Section_NID, Section_Instructors, Session, Grade, Subject, Assessment_type,
-- Item_ID, Item_Name, School_ID) -> Total_Possible_Point_By_Question.
max_values AS (
  SELECT
    school_id, section_nid, section_instructors,
    session, grade, subject, assessment_type, item_id, item_name,
    MAX(max_total_possible_point_by_question)    AS total_possible_point_by_question
  FROM user_question
  GROUP BY school_id, section_nid, section_instructors,
           session, grade, subject, assessment_type, item_id, item_name
),
-- Step 3: Cube_User_Overall_Summary per (Session, Grade, Subject, Assessment_type,
-- Item_Name, School_ID): sum across Total_Possible_Point_By_Question and
-- Total_Score_By_Question -> _by_overall.
overall AS (
  SELECT
    school_id, session, grade, subject, assessment_type, item_name,
    SUM(total_possible_point_by_question)        AS total_possible_point_by_overall,
    SUM(total_score_by_question)                 AS total_score_by_overall
  FROM (
    SELECT mv.*, uq.total_score_by_question
    FROM max_values mv
    LEFT JOIN user_question uq
      ON uq.school_id = mv.school_id
     AND uq.section_nid IS NOT DISTINCT FROM mv.section_nid
     AND uq.section_instructors IS NOT DISTINCT FROM mv.section_instructors
     AND uq.session = mv.session AND uq.grade = mv.grade
     AND uq.subject = mv.subject AND uq.assessment_type = mv.assessment_type
     AND uq.item_id = mv.item_id AND uq.item_name = mv.item_name
  ) j
  GROUP BY school_id, session, grade, subject, assessment_type, item_name
),
-- Step 4: Cube_User_OverallYear_Summary per (Session, Grade, Subject,
-- Assessment_type, School_ID).
overall_year AS (
  SELECT
    school_id, session, grade, subject, assessment_type,
    SUM(total_possible_point_by_overall)         AS total_possible_point_by_overall_year,
    SUM(total_score_by_overall)                  AS total_score_by_overall_year
  FROM overall
  GROUP BY school_id, session, grade, subject, assessment_type
),
-- Step 5: Cube_UserCount_Item_Summary: countDistinct(User_UID) per item.
user_count_item AS (
  SELECT
    school_id, item_id,
    COUNT(DISTINCT user_uid) AS count_student
  FROM fact_join_qd
  GROUP BY school_id, item_id
),
-- Step 6: Cube_User_Item_Summary: Total_Score_By_Item = round(sum(Points_Received),2);
-- Max_Possible_Point_By_Item = max(Total_Points); then
-- Total_Possible_Point_By_Item = countStudent * Max_Possible_Point_By_Item.
user_item_score AS (
  SELECT
    school_id, item_id,
    ROUND(SUM(points_received), 2)                  AS total_score_by_item,
    MAX(total_points_num)                            AS max_possible_point_by_item
  FROM fact_join_qd
  GROUP BY school_id, item_id
),
user_item AS (
  SELECT
    uis.school_id, uis.item_id,
    uci.count_student * uis.max_possible_point_by_item AS total_possible_point_by_item,
    uis.total_score_by_item
  FROM user_item_score uis
  LEFT JOIN user_count_item uci
    ON uci.school_id = uis.school_id AND uci.item_id = uis.item_id
),
-- Step 7: Cube_User_Standard_Summary per (Session, Grade, Subject,
-- Assessment_type, Item_Name, Standards, School_ID).
user_standard AS (
  SELECT
    school_id, session, grade, subject, assessment_type, item_name, standards,
    ROUND(SUM(total_points_num), 2)              AS total_possible_point_by_standard,
    ROUND(SUM(points_received), 2)               AS total_score_by_standard
  FROM fact_join_qd
  GROUP BY school_id, session, grade, subject, assessment_type, item_name, standards
),
-- Step 8: Cube_User_Section_Summary per (Section_NID, Section_Instructors,
-- Session, Grade, Subject, Assessment_type, Item_ID, Item_Name, School_ID).
user_section AS (
  SELECT
    f.school_id, f.section_nid, sm.section_instructors,
    f.session, f.grade, f.subject, f.assessment_type, f.item_id, f.item_name,
    ROUND(SUM(f.total_points_num), 2)            AS total_possible_point_by_section,
    ROUND(SUM(f.points_received), 2)             AS total_score_by_section
  FROM fact_join_qd f
  LEFT JOIN section_meta sm
    ON sm.school_id   = f.school_id
   AND sm.section_nid = f.section_nid
  GROUP BY f.school_id, f.section_nid, sm.section_instructors,
           f.session, f.grade, f.subject, f.assessment_type, f.item_id, f.item_name
),
-- Step 9: BASE — Cube_User_Summary per (Section_NID, Section_Instructors,
-- Session, Grade, Subject, Assessment_type, User_UID, User_Name, Item_ID,
-- Item_Name, Question_ID, Question_No, Standards, School_ID).
base AS (
  SELECT
    f.school_id, f.school_id_csv, f.section_nid, sm.section_instructors,
    f.session, f.grade, f.subject, f.assessment_type,
    f.user_uid, f.user_name,
    f.item_id, f.item_name, f.question_id, f.question_no, f.standards,
    ROUND(SUM(f.total_points_num), 2) AS total_possible_point,
    ROUND(SUM(f.points_received), 2)  AS total_score
  FROM fact_join_qd f
  LEFT JOIN section_meta sm
    ON sm.school_id   = f.school_id
   AND sm.section_nid = f.section_nid
  GROUP BY f.school_id, f.school_id_csv, f.section_nid, sm.section_instructors,
           f.session, f.grade, f.subject, f.assessment_type,
           f.user_uid, f.user_name,
           f.item_id, f.item_name, f.question_id, f.question_no, f.standards
),
-- Step 10: Per-student grand total (User_Possible_Point) and per-(school,
-- section, year) grand total (User_Overall_Possible_Point).
user_possible AS (
  SELECT
    school_id, user_uid,
    SUM(total_possible_point) AS user_possible_point
  FROM base
  GROUP BY school_id, user_uid
),
user_overall_possible AS (
  SELECT
    school_id, section_nid, session, grade, subject, assessment_type,
    SUM(total_possible_point) AS user_overall_possible_point
  FROM base
  GROUP BY school_id, section_nid, session, grade, subject, assessment_type
)
-- Final SELECT: join ALL aggregates onto base.
SELECT
  encode(digest(
    CONCAT_WS(', ',
      COALESCE(b.section_nid,         'DEFAULT_SECTION_NID'),
      COALESCE(b.session,             'DEFAULT_SESSION'),
      COALESCE(b.grade,               'DEFAULT_GRADE'),
      COALESCE(b.subject,             'DEFAULT_SUBJECT'),
      COALESCE(b.assessment_type,     'DEFAULT_ASSESSMENT_TYPE'),
      COALESCE(b.user_uid,            'DEFAULT_USER_UID'),
      COALESCE(b.user_name,           'DEFAULT_USER_NAME'),
      COALESCE(b.item_id,             'DEFAULT_ITEM_ID'),
      COALESCE(b.item_name,           'DEFAULT_ITEM_NAME'),
      COALESCE(b.question_id,         'DEFAULT_QUESTION_ID'),
      COALESCE(b.question_no,         'DEFAULT_QUESTION_NO'),
      COALESCE(b.standards,           'DEFAULT_STANDARDS'),
      COALESCE(b.school_id::text,     'DEFAULT_SCHOOL_ID')
    ),
    'sha256'
  ), 'hex')                                          AS id,
  b.school_id,
  b.school_id_csv,
  b.section_nid,
  b.section_instructors,
  b.session, b.grade, b.subject, b.assessment_type,
  b.user_uid, b.user_name,
  b.item_id, b.item_name, b.question_id, b.question_no, b.standards,
  b.total_possible_point,
  b.total_score,
  mv.total_possible_point_by_question,
  uq.total_score_by_question,
  ov.total_possible_point_by_overall,
  ov.total_score_by_overall,
  oy.total_possible_point_by_overall_year,
  oy.total_score_by_overall_year,
  ui.total_possible_point_by_item,
  ui.total_score_by_item,
  us.total_possible_point_by_section,
  us.total_score_by_section,
  ust.total_possible_point_by_standard,
  ust.total_score_by_standard,
  uci.count_student,
  up.user_possible_point,
  uop.user_overall_possible_point,
  sh.student_name_hash,
  dsh.teacher_name_hash
FROM base b
LEFT JOIN max_values mv
  ON mv.school_id           = b.school_id
 AND mv.section_nid IS NOT DISTINCT FROM b.section_nid
 AND mv.section_instructors IS NOT DISTINCT FROM b.section_instructors
 AND mv.session             = b.session
 AND mv.grade               = b.grade
 AND mv.subject             = b.subject
 AND mv.assessment_type     = b.assessment_type
 AND mv.item_id             = b.item_id
 AND mv.item_name           = b.item_name
LEFT JOIN user_question uq
  ON uq.school_id           = b.school_id
 AND uq.section_nid IS NOT DISTINCT FROM b.section_nid
 AND uq.section_instructors IS NOT DISTINCT FROM b.section_instructors
 AND uq.session             = b.session
 AND uq.grade               = b.grade
 AND uq.subject             = b.subject
 AND uq.assessment_type     = b.assessment_type
 AND uq.user_uid            = b.user_uid
 AND uq.user_name IS NOT DISTINCT FROM b.user_name
 AND uq.item_id             = b.item_id
 AND uq.item_name           = b.item_name
LEFT JOIN overall ov
  ON ov.school_id           = b.school_id
 AND ov.session             = b.session
 AND ov.grade               = b.grade
 AND ov.subject             = b.subject
 AND ov.assessment_type     = b.assessment_type
 AND ov.item_name           = b.item_name
LEFT JOIN overall_year oy
  ON oy.school_id           = b.school_id
 AND oy.session             = b.session
 AND oy.grade               = b.grade
 AND oy.subject             = b.subject
 AND oy.assessment_type     = b.assessment_type
LEFT JOIN user_count_item uci
  ON uci.school_id          = b.school_id
 AND uci.item_id            = b.item_id
LEFT JOIN user_item ui
  ON ui.school_id           = b.school_id
 AND ui.item_id             = b.item_id
LEFT JOIN user_section us
  ON us.school_id           = b.school_id
 AND us.section_nid IS NOT DISTINCT FROM b.section_nid
 AND us.section_instructors IS NOT DISTINCT FROM b.section_instructors
 AND us.session             = b.session
 AND us.grade               = b.grade
 AND us.subject             = b.subject
 AND us.assessment_type     = b.assessment_type
 AND us.item_id             = b.item_id
 AND us.item_name           = b.item_name
LEFT JOIN user_standard ust
  ON ust.school_id          = b.school_id
 AND ust.session            = b.session
 AND ust.grade              = b.grade
 AND ust.subject            = b.subject
 AND ust.assessment_type    = b.assessment_type
 AND ust.item_name          = b.item_name
 AND ust.standards          = b.standards
LEFT JOIN user_possible up
  ON up.school_id           = b.school_id
 AND up.user_uid            = b.user_uid
LEFT JOIN user_overall_possible uop
  ON uop.school_id          = b.school_id
 AND uop.section_nid IS NOT DISTINCT FROM b.section_nid
 AND uop.session            = b.session
 AND uop.grade              = b.grade
 AND uop.subject            = b.subject
 AND uop.assessment_type    = b.assessment_type
LEFT JOIN dim_student_hash sh
  ON sh.school_id           = b.school_id
 AND sh.user_uid            = b.user_uid
LEFT JOIN dim_section_hash dsh
  ON dsh.school_id          = b.school_id
 AND dsh.section_nid IS NOT DISTINCT FROM b.section_nid
WHERE b.school_id IS NOT NULL;
