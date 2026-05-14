-- Staging: raw_user -> stg_user.
-- Phase 1 of the project hasn't populated raw_user yet (sync_users.py is
-- Phase 7 / D3). This file is therefore a TRUNCATE+INSERT pass-through so
-- the stg_user table is consistently rebuilt every run regardless of
-- whether raw_user is empty.
-- When sync_users.py lands, the same SELECT will pick up all rich user
-- fields (name_title, picture_url, grad_year, etc.) automatically.
--
-- Notebook reference: section 4 — `df_User = oea.load(...users)` (line 798
-- of Schoology_py.ipynb, see 40_schoology_py_spec.md).

TRUNCATE TABLE stg_user;

INSERT INTO stg_user (
  school_id, uid, id, school_uid,
  name_title, name_first, name_first_preferred, use_preferred_first_name,
  name_middle, name_middle_show, name_last, name_display,
  primary_email, picture_url, gender, position, grad_year,
  username, password_hash, role_id, tz_offset, tz_name, language,
  child_uids, user_school_id, is_active
)
SELECT
  ru.school_id,
  NULLIF(TRIM(ru.uid), ''),
  NULLIF(TRIM(ru.id), ''),
  NULLIF(TRIM(ru.school_uid), ''),
  NULLIF(TRIM(ru.name_title), ''),
  NULLIF(TRIM(ru.name_first), ''),
  NULLIF(TRIM(ru.name_first_preferred), ''),
  ru.use_preferred_first_name,
  NULLIF(TRIM(ru.name_middle), ''),
  ru.name_middle_show,
  NULLIF(TRIM(ru.name_last), ''),
  NULLIF(TRIM(ru.name_display), ''),
  NULLIF(TRIM(ru.primary_email), ''),
  NULLIF(TRIM(ru.picture_url), ''),
  NULLIF(TRIM(ru.gender), ''),
  NULLIF(TRIM(ru.position), ''),
  NULLIF(TRIM(ru.grad_year), ''),
  NULLIF(TRIM(ru.username), ''),
  ru.password_hash,
  NULLIF(TRIM(ru.role_id), ''),
  NULLIF(TRIM(ru.tz_offset), ''),
  NULLIF(TRIM(ru.tz_name), ''),
  NULLIF(TRIM(ru.language), ''),
  ru.child_uids,
  s.schoology_school_id,
  ru.is_active
FROM raw_user ru
JOIN schools s ON s.school_id = ru.school_id;
