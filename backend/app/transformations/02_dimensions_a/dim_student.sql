-- dim_student — one row per (school_id, uid) where role_id = 286170 (Student).
-- Notebook line 859 (40_schoology_py_spec.md §4.2): filters df_User by
-- role_id=='286170' and selects 23 user fields.
--
-- Phase 1 has not yet populated raw_user/stg_user (sync_users.py lands in
-- Phase 7 — D3). Until then we synthesise minimal student rows from
-- stg_student_submission so downstream transforms (and the fact build) have
-- something to join. When stg_user is populated, those rich fields take
-- precedence on conflict.
--
-- Two-step UPSERT:
--   (1) primary source: stg_user filtered to role 286170, full field set.
--   (2) fallback:       stg_student_submission distinct user_uid where
--                       user_role_id = '286170', minimal field set, only for
--                       (school_id, uid) NOT already in stg_user.

-- (1) From stg_user (rich fields when sync_users.py is in place)
INSERT INTO dim_student (
  uid, school_id, id, school_id_csv, school_uid,
  name_title, name_first, name_first_preferred, use_preferred_first_name,
  name_middle, name_middle_show, name_last, name_display,
  primary_email, picture_url, gender, position, grad_year,
  username, password_hash, role_id, tz_offset, tz_name, language
)
SELECT
  u.uid,
  u.school_id,
  u.id,
  u.user_school_id,
  u.school_uid,
  u.name_title, u.name_first, u.name_first_preferred, u.use_preferred_first_name,
  u.name_middle, u.name_middle_show, u.name_last, u.name_display,
  u.primary_email, u.picture_url, u.gender, u.position, u.grad_year,
  u.username, u.password_hash, u.role_id, u.tz_offset, u.tz_name, u.language
FROM stg_user u
-- Per-school student role filter (schools.student_role_id; default 286170 for
-- Athenian). Replaces the former hardcoded '286170' so each school keeps its
-- own Student role id (Schoology assigns a different id per building).
JOIN schools sch ON sch.school_id = u.school_id
WHERE u.role_id = sch.student_role_id
  AND u.uid IS NOT NULL
ON CONFLICT (school_id, uid) DO UPDATE
SET id                       = EXCLUDED.id,
    school_id_csv            = EXCLUDED.school_id_csv,
    school_uid               = EXCLUDED.school_uid,
    name_title               = EXCLUDED.name_title,
    name_first               = EXCLUDED.name_first,
    name_first_preferred     = EXCLUDED.name_first_preferred,
    use_preferred_first_name = EXCLUDED.use_preferred_first_name,
    name_middle              = EXCLUDED.name_middle,
    name_middle_show         = EXCLUDED.name_middle_show,
    name_last                = EXCLUDED.name_last,
    name_display             = EXCLUDED.name_display,
    primary_email            = EXCLUDED.primary_email,
    picture_url              = EXCLUDED.picture_url,
    gender                   = EXCLUDED.gender,
    position                 = EXCLUDED.position,
    grad_year                = EXCLUDED.grad_year,
    username                 = EXCLUDED.username,
    password_hash            = EXCLUDED.password_hash,
    role_id                  = EXCLUDED.role_id,
    tz_offset                = EXCLUDED.tz_offset,
    tz_name                  = EXCLUDED.tz_name,
    language                 = EXCLUDED.language;

-- (2) Fallback from stg_student_submission for (school_id, uid) not in stg_user
INSERT INTO dim_student (
  uid, school_id, school_id_csv,
  name_first, name_last, username, role_id
)
SELECT DISTINCT
  src.user_uid                 AS uid,
  src.school_id,
  src.user_school_id           AS school_id_csv,
  src.first_name               AS name_first,
  src.last_name                AS name_last,
  src.username,
  src.user_role_id             AS role_id
FROM stg_student_submission src
JOIN schools sch ON sch.school_id = src.school_id
WHERE src.user_role_id = sch.student_role_id
  AND src.user_uid IS NOT NULL
ON CONFLICT (school_id, uid) DO UPDATE
SET school_id_csv = COALESCE(dim_student.school_id_csv, EXCLUDED.school_id_csv),
    name_first    = COALESCE(dim_student.name_first,    EXCLUDED.name_first),
    name_last     = COALESCE(dim_student.name_last,     EXCLUDED.name_last),
    username      = COALESCE(dim_student.username,      EXCLUDED.username),
    role_id       = COALESCE(dim_student.role_id,       EXCLUDED.role_id);
