#!/usr/bin/env python3
"""Seed demo auth users with school memberships to exercise tenant isolation.

Creates email/password users (confirmed) and a matching auth.identities row so
they can log in via the normal flow. The handle_new_user trigger auto-creates a
profile + assigns the platform 'user' role; we then attach school membership in
public.user_schools. The JWT claims hook turns membership into school_ids /
primary_school_id at login.

All demo users share the password below. Idempotent: re-running upserts.

Usage:
    backend/venv/bin/python supabase/seeds/seed_demo_users.py
"""
from __future__ import annotations

import psycopg2

PG = "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
DEMO_PASSWORD = "GainsDemo123!"

# (email, school building_id, school_role within that school)
DEMO_USERS = [
    ("teacher.oakwood@gains.demo", "synth-001", "teacher"),
    ("student.oakwood@gains.demo", "synth-001", "student"),
    ("admin.riverside@gains.demo", "synth-000", "admin"),
    ("teacher.lincoln@gains.demo", "synth-003", "teacher"),
]


def main() -> int:
    conn = psycopg2.connect(PG)
    conn.autocommit = False
    cur = conn.cursor()

    for email, building_id, school_role in DEMO_USERS:
        cur.execute(
            "SELECT school_id, name FROM schools WHERE schoology_building_id=%s",
            (building_id,),
        )
        row = cur.fetchone()
        if not row:
            print(f"  SKIP {email}: school {building_id} not found")
            continue
        school_id, school_name = row

        # Upsert the auth user (bcrypt password via pgcrypto).
        cur.execute("SELECT id FROM auth.users WHERE email=%s", (email,))
        existing = cur.fetchone()
        if existing:
            user_id = existing[0]
            cur.execute(
                "UPDATE auth.users SET encrypted_password = crypt(%s, gen_salt('bf')), "
                "email_confirmed_at = now(), updated_at = now() WHERE id=%s",
                (DEMO_PASSWORD, user_id),
            )
        else:
            cur.execute(
                """
                INSERT INTO auth.users (
                    id, instance_id, aud, role, email, encrypted_password,
                    email_confirmed_at, raw_app_meta_data, raw_user_meta_data,
                    created_at, updated_at,
                    -- GoTrue scans these token columns as NOT NULL strings;
                    -- manually-inserted rows must set them to '' or login 500s
                    -- with "Database error querying schema".
                    confirmation_token, recovery_token, email_change,
                    email_change_token_new, email_change_token_current,
                    phone_change, phone_change_token, reauthentication_token)
                VALUES (
                    uuid_generate_v7(), '00000000-0000-0000-0000-000000000000',
                    'authenticated', 'authenticated', %s,
                    crypt(%s, gen_salt('bf')), now(),
                    '{"provider":"email","providers":["email"]}'::jsonb,
                    jsonb_build_object('full_name', %s),
                    now(), now(),
                    '', '', '', '', '', '', '', '')
                RETURNING id
                """,
                (email, DEMO_PASSWORD, email.split("@")[0].replace(".", " ").title()),
            )
            user_id = cur.fetchone()[0]
            # identities row so GoTrue recognises the email provider login
            cur.execute(
                """
                INSERT INTO auth.identities (
                    id, provider_id, user_id, identity_data, provider,
                    last_sign_in_at, created_at, updated_at)
                VALUES (
                    uuid_generate_v7(), %s, %s,
                    jsonb_build_object('sub', %s::text, 'email', %s, 'email_verified', true),
                    'email', now(), now(), now())
                ON CONFLICT DO NOTHING
                """,
                (str(user_id), user_id, str(user_id), email),
            )

        # Attach membership (primary).
        cur.execute(
            """
            INSERT INTO public.user_schools (user_id, school_id, school_role, is_primary)
            VALUES (%s, %s, %s, true)
            ON CONFLICT (user_id, school_id)
            DO UPDATE SET school_role = EXCLUDED.school_role, is_primary = true
            """,
            (user_id, school_id, school_role),
        )
        conn.commit()
        print(f"  {email:32s} -> {school_name} ({school_role})")

    cur.close()
    conn.close()
    print(f"\nDemo users seeded. Password for all: {DEMO_PASSWORD}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
