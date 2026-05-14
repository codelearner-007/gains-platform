-- dim_teacher — one row per (school_id, uid) where role_id = 286168 (Teacher).
-- Notebook line 875 (40_schoology_py_spec.md §4.2): same shape as dim_student
-- except `school_uid` is dropped (teachers do not have it in Schoology).
--
-- Fallback strategy: when stg_user is empty (Phase 1 only ingests CSVs),
-- stg_student_submission has the teacher NAME inline as `section_instructors`
-- but NOT a uid. We therefore CANNOT synthesise a teacher row from CSVs alone
-- (no uid -> no PK). dim_teacher is intentionally left empty until
-- sync_users.py (Phase 7) populates stg_user. This matches the notebook,
-- which only builds dim_teacher from df_User.

INSERT INTO dim_teacher (
  uid, school_id, id, school_id_csv,
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
  u.name_title, u.name_first, u.name_first_preferred, u.use_preferred_first_name,
  u.name_middle, u.name_middle_show, u.name_last, u.name_display,
  u.primary_email, u.picture_url, u.gender, u.position, u.grad_year,
  u.username, u.password_hash, u.role_id, u.tz_offset, u.tz_name, u.language
FROM stg_user u
WHERE u.role_id = '286168'
  AND u.uid IS NOT NULL
ON CONFLICT (school_id, uid) DO UPDATE
SET id                       = EXCLUDED.id,
    school_id_csv            = EXCLUDED.school_id_csv,
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
