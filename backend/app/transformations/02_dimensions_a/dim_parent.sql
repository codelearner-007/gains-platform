-- dim_parent — one row per (school_id, uid) where role_id = 286172 (Parent).
-- Notebook line 884 (40_schoology_py_spec.md §4.2): same field set as
-- dim_student plus `child_uids`.
--
-- Parents do not appear in submission CSVs (only students submit), so this
-- table can ONLY be populated from stg_user once Phase 7 sync_users.py lands.
-- That matches the notebook, which builds dim_parent from df_User only.

INSERT INTO dim_parent (
  uid, school_id, id, school_id_csv, school_uid,
  name_title, name_first, name_first_preferred, use_preferred_first_name,
  name_middle, name_middle_show, name_last, name_display,
  primary_email, picture_url, gender, position, grad_year,
  username, password_hash, role_id, tz_offset, tz_name, language, child_uids
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
  u.username, u.password_hash, u.role_id, u.tz_offset, u.tz_name, u.language,
  u.child_uids
FROM stg_user u
WHERE u.role_id = '286172'
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
    language                 = EXCLUDED.language,
    child_uids               = EXCLUDED.child_uids;
