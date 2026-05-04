# Next.js + FastAPI + Supabase SaaS Starter Template

A production-ready SaaS starter template with authentication, role-based access control, admin panel, and audit logging built on modern technologies.

## Features

- **Authentication** -- Email/password, **Google OAuth (PKCE)**, **email magic link**, MFA/TOTP, email verification, password reset
- **Admin Panel** -- Dashboard with stats, user management, RBAC configuration, audit logs
- **Role-Based Access Control** -- 13 permissions across 4 modules, hierarchical roles, JWT claims hook (first registered user becomes `super_admin` automatically)
- **User Settings** -- Profile, password, MFA, theme + timezone preferences, active sessions
- **Audit Logging** -- Tamper-resistant activity trail (service_role-only RLS, paginated viewer, ban/unban/delete/reset/change-password actions all logged)
- **Branded Email Templates** -- Custom confirm / recovery / email-change / magic-link templates served by Supabase
- **Premium Design System** -- Indigo/violet brand, deep dark mode, restrained palette inspired by Linear/Stripe/Resend
- **Dark Mode** -- System-aware theme switching via next-themes
- **Docker Support** -- Dockerfiles and docker-compose for containerized deployment

## Tech Stack

| Layer | Technology |
|-------|-----------|
| Frontend | Next.js 16.1, React 19, TypeScript, Tailwind CSS v4, shadcn/ui |
| Backend | FastAPI 0.128, SQLAlchemy 2.0 (async), Pydantic v2, slowapi |
| Database | Supabase PostgreSQL 15, Row-Level Security, UUID v7 |
| Auth | Supabase Auth (SSR cookies, JWKS verification, MFA/TOTP) |

## Architecture

```
Browser
  |
  v
Next.js (port 3000)                     FastAPI (port 8000)
  - Auth API routes (/api/auth/*)          - All database operations
  - User admin routes (/api/users/*)       - Business logic (services)
  - Rewrites /api/v1/* to FastAPI ------>  - Repository pattern
  - UI rendering                           - RBAC permission guards
  |                                        |
  v                                        v
Supabase (ports 56321-56327)
  - PostgreSQL database
  - Auth (GoTrue)
  - JWT claims hook (injects permissions)
```

Key design decisions:

- **No CORS needed.** Next.js rewrites `/api/v1/*` to FastAPI, so all requests appear same-origin.
- **Next.js handles auth only.** Login, register, magic link, OAuth callback, MFA, password reset, and user admin actions (ban, delete, resend verification).
- **FastAPI handles all database operations.** Using the Router > Service > Repository > Database pattern.
- **Supabase client is never used in frontend components.** Only in API routes and middleware.

## Quick Start (Local Development)

### Prerequisites

- Node.js 20+
- Python 3.11+
- Docker (required by Supabase CLI)
- Supabase CLI (`npm install -g supabase`)
- Git

### 1. Clone and Install

```bash
git clone <repo-url>
cd saas-starter-template
```

Install frontend dependencies:

```bash
cd frontend
cp .env.example .env.local
npm install
```

Install backend dependencies:

```bash
cd ../backend
cp .env.example .env
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Start Supabase

From the project root:

```bash
npx supabase start
```

This starts the local Supabase stack on custom ports to avoid conflicts with other projects:

| Service | Port |
|---------|------|
| API (Kong) | 56321 |
| Database (PostgreSQL) | 56322 |
| Studio (Dashboard) | 56323 |
| Inbucket (Email testing) | 56324 |
| SMTP | 56325 |
| POP3 | 56326 |
| Analytics | 56327 |

The `.env.example` files are pre-configured for these local ports. No changes needed for local development.

### 3. Run Migrations and Seed Data

```bash
npx supabase db reset --local
```

This applies all four migrations and seeds the database with default roles and permissions:

- `uuid_v7_function` -- Installs the UUID v7 generator function for time-ordered primary keys
- `rbac_system` -- Creates roles, permissions, user_roles, role_permissions, user_profiles, and audit_logs tables with RLS
- `jwt_claims_hook` -- Adds a PostgreSQL function that injects role and permissions into JWT tokens on every token issuance
- `user_preferences` -- Adds timezone/preferences columns to user_profiles and creates the avatars storage bucket

### 4. Start Development Servers

Open two terminal windows:

```bash
# Terminal 1: Frontend (port 3000)
cd frontend
npm run dev
```

```bash
# Terminal 2: Backend (port 8000)
cd backend
uvicorn app.main:app --reload --port 8000
```

### 5. First User Setup

1. Open http://localhost:3000 and register a new account (email/password **or** magic link).
2. Check the email inbox at http://localhost:56324 (Mailpit) for the confirmation / sign-in email.
3. Click the link to verify your account and sign in.

The **first registered user is automatically promoted to `super_admin`**. Subsequent users get the base `user` role.

To manually promote an existing user to `super_admin`:

```bash
psql "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
```

```sql
SELECT id, email FROM auth.users;

UPDATE user_roles
SET role_id = (SELECT id FROM roles WHERE name = 'super_admin')
WHERE user_id = 'USER-UUID-HERE';
```

The user must log out and log back in after a role change for the new permissions to take effect (permissions are embedded in the JWT token).

### 6. Optional: Enable Google OAuth

Google sign-in is wired but disabled until credentials are provided.

1. Create OAuth credentials at <https://console.cloud.google.com/apis/credentials>.
2. Add an authorized redirect URI: `http://127.0.0.1:56321/auth/v1/callback` (and your production equivalent).
3. Add to your local environment (e.g. a `supabase/.env` that the CLI reads on `supabase start`):

   ```bash
   SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID=...
   SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET=...
   ```

4. Restart Supabase: `npx supabase stop && npx supabase start`.
5. The "Continue with Google" button on `/auth/login` and `/auth/register` is now live. The provider list is controlled by `NEXT_PUBLIC_SSO_PROVIDERS` (csv: `google`, `github`).

The OAuth callback (`/api/auth/callback`) enforces an allowlist on the `next` redirect parameter, signs the user out if MFA verification fails, and rate-limits the POST exchange path.

## Production Deployment (Supabase Cloud)

### 1. Create a Supabase Project

1. Go to https://supabase.com/dashboard and create a new project.
2. Note the following values from Project Settings > API:
   - Project URL (e.g., `https://abcdef.supabase.co`)
   - `anon` public key
   - `service_role` secret key
   - JWT Secret (Project Settings > API > JWT Settings)

### 2. Link and Deploy Migrations

```bash
npx supabase login
npx supabase link --project-ref YOUR_PROJECT_REF
npx supabase db push
```

### 3. Seed Production Data

Run the seed file against your production database to create the default roles and permissions:

```bash
psql "YOUR_PRODUCTION_DATABASE_URL" -f supabase/seeds/rbac_seed.sql
```

You can find your production database URL in Supabase Dashboard > Project Settings > Database.

### 4. Configure Environment Variables

Update `frontend/.env.local`:

```bash
NEXT_PUBLIC_SUPABASE_URL=https://your-project.supabase.co
NEXT_PUBLIC_SUPABASE_ANON_KEY=your-anon-key
PRIVATE_SUPABASE_SERVICE_KEY=your-service-role-key
NEXT_PUBLIC_SITE_URL=https://yourdomain.com
NEXT_PUBLIC_PRODUCTNAME=YourAppName
```

Update `backend/.env`:

```bash
DATABASE_URL=postgresql://postgres:YOUR_PASSWORD@db.YOUR_PROJECT_REF.supabase.co:5432/postgres
SUPABASE_URL=https://your-project.supabase.co
SUPABASE_ANON_KEY=your-anon-key
SUPABASE_SERVICE_KEY=your-service-role-key
JWT_SECRET=your-jwt-secret
USE_JWKS=true
ENVIRONMENT=production
LOG_LEVEL=WARNING
```

### 5. Deploy the Application

**Frontend (Vercel):**

```bash
cd frontend
vercel deploy --prod
```

Set `NEXT_PUBLIC_API_URL` in Vercel environment variables to point to your deployed backend URL. This is used by `next.config.ts` to proxy `/api/v1/*` requests.

**Backend (Railway, Render, or Fly.io):**

Deploy the `backend/` directory using the included `Dockerfile`. Set the start command to:

```bash
uvicorn app.main:app --host 0.0.0.0 --port 8000
```

## Docker Deployment

A `docker-compose.yml` is included for containerized deployment of the frontend and backend:

```bash
# Create a .env file in the project root with your Supabase credentials
docker-compose up --build
```

The compose file starts both services:

- Frontend on port 3000
- Backend on port 8000

Note: The compose file does not include Supabase itself. You need either a local Supabase instance (`npx supabase start`) or a Supabase Cloud project.

## RBAC System

### Default Roles

| Role | Hierarchy Level | Description |
|------|----------------|-------------|
| `super_admin` | 10000 | Full system access, all 13 permissions, system-protected |
| `user` | 100 | Base role, no admin permissions |

Both roles are system roles (`is_system = true`) and cannot be deleted through the API. You can create custom roles with any hierarchy level through the admin panel.

### Permissions (13 total)

| Module | Permissions |
|--------|------------|
| users | `read_all`, `update_all`, `delete_all`, `assign_roles` |
| roles | `create`, `read`, `update`, `delete` |
| permissions | `create`, `read`, `update`, `delete` |
| audit | `read` |

### How It Works

1. Roles and permissions are stored in PostgreSQL tables with a many-to-many relationship (`role_permissions` junction table).
2. A JWT claims hook (`custom_access_token_hook`) runs on every token issuance and injects the user's role name, hierarchy level, and permission strings into the JWT payload.
3. The FastAPI backend validates permissions using dependency injection: `dependencies=[Depends(require_permission("roles:create"))]`.
4. The frontend reads permissions from the JWT claims via `useAdminClaims()` and conditionally renders UI elements with `hasPermission()`.

## Project Structure

```
saas-starter-template/
|
|-- frontend/
|   |-- src/
|   |   |-- app/                    # Pages and API routes
|   |   |   |-- admin/              # Admin panel (dynamic [module] route)
|   |   |   |-- app/                # Authenticated app pages (dashboard, settings)
|   |   |   |-- auth/               # Auth pages (login, register, 2fa, verify-email)
|   |   |   |-- api/
|   |   |       |-- auth/           # Auth API routes (login, register, MFA, etc.)
|   |   |       |-- users/[userId]/ # User admin actions (ban, delete, reset-password)
|   |   |-- components/
|   |   |   |-- admin/modules/      # Admin UI (rbac, users, audit)
|   |   |   |-- common/             # Shared components (SiteNav, SiteFooter)
|   |   |   |-- forms/              # Form components (auth, user)
|   |   |   |-- ui/                 # shadcn/ui primitives
|   |   |-- lib/
|   |       |-- services/           # API service layer
|   |       |-- schemas/            # Zod validation schemas
|   |       |-- supabase/           # Supabase clients (API routes only)
|   |       |-- context/            # React context (GlobalContext)
|   |       |-- utils/              # CSRF, MFA, rate-limit, audit-log, RBAC helpers
|   |-- next.config.ts              # API rewrite rules (/api/v1/* -> FastAPI)
|
|-- backend/
|   |-- app/
|   |   |-- api/v1/                 # FastAPI route handlers
|   |   |   |-- auth.py             # GET /auth/me
|   |   |   |-- profile.py          # GET/PATCH /profile, POST /profile/avatar
|   |   |   |-- users.py            # GET /users/stats, /users/with-roles
|   |   |   |-- user_roles.py       # User role assignment
|   |   |   |-- roles.py            # CRUD + permission assignment
|   |   |   |-- permissions.py      # List (grouped) + create/delete
|   |   |   |-- audit.py            # GET /audit/logs (paginated, filterable), GET /audit/modules
|   |   |   |-- dashboard.py        # GET /dashboard/stats
|   |   |   |-- sessions.py         # List + revoke active sessions
|   |   |-- services/               # Business logic layer
|   |   |-- repositories/           # Data access layer (SQLAlchemy queries)
|   |   |-- models/                 # SQLAlchemy ORM models
|   |   |-- schemas/                # Pydantic schemas (request/ and response/)
|   |   |-- core/                   # Config, security, dependencies, rate limiting
|   |   |-- db/                     # Database session management
|   |-- requirements.txt
|   |-- Dockerfile
|
|-- supabase/
|   |-- migrations/                 # 4 SQL migration files
|   |   |-- 20260201000000_uuid_v7_function.sql
|   |   |-- 20260201000001_rbac_system.sql       # tables + RLS + first-user-is-super-admin trigger + system role seeding
|   |   |-- 20260201000002_jwt_claims_hook.sql
|   |   |-- 20260201000009_user_preferences.sql  # timezone/preferences columns + avatars storage bucket
|   |-- seeds/
|   |   |-- rbac_seed.sql           # 13 permissions (system roles live in the migration)
|   |-- templates/                  # Branded email templates (confirmation, recovery, email_change, magic_link)
|   |-- config.toml                 # Supabase auth + ports + provider config
|
|-- docker-compose.yml              # Frontend + Backend containers
```

## Environment Variables

### Frontend (`frontend/.env.local`)

| Variable | Description | Required |
|----------|-------------|----------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase API URL | Yes |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key | Yes |
| `PRIVATE_SUPABASE_SERVICE_KEY` | Supabase service role key (server-side only) | Yes |
| `NEXT_PUBLIC_PRODUCTNAME` | Application display name | Yes |
| `NEXT_PUBLIC_API_URL` | FastAPI backend URL (used by Server Components) | No (defaults to localhost:8000) |
| `NEXT_PUBLIC_SITE_URL` | Public site URL (used to build OAuth/email-link redirect targets — must be set in production) | Production |
| `NEXT_PUBLIC_SSO_PROVIDERS` | Comma-separated list of enabled SSO providers (e.g. `google,github`). Provider must also be enabled in `supabase/config.toml` and have credentials. | No (defaults to `google`) |
| `FRONTEND_REDIS_URL` | Redis URL for rate limiting on Next.js API routes; when unset, rate limiting is bypassed (intentional dev opt-out) | Production |
| `FRONTEND_RATE_LIMIT_FAIL_OPEN` | When Redis is configured but unreachable: `true` to allow requests, `false` (default) to fail-closed with 503 | No |

### Backend (`backend/.env`)

| Variable | Description | Required |
|----------|-------------|----------|
| `DATABASE_URL` | PostgreSQL connection string (port 56322 locally) | Yes |
| `SUPABASE_URL` | Supabase API URL (port 56321 locally) | Yes |
| `SUPABASE_ANON_KEY` | Supabase anonymous key | Yes |
| `SUPABASE_SERVICE_KEY` | Supabase service role key (used for avatar uploads to Storage) | Yes |
| `JWT_SECRET` | JWT signing secret (from Supabase project settings) | Yes |
| `USE_JWKS` | Use JWKS endpoint for JWT verification (`true` recommended) | Yes |
| `ENVIRONMENT` | `development` or `production` | No |
| `LOG_LEVEL` | Logging level: `DEBUG`, `INFO`, `WARNING` | No |
| `DB_POOL_SIZE` | SQLAlchemy connection pool size (default: 10) | No |
| `DB_MAX_OVERFLOW` | Max overflow connections (default: 20) | No |
| `ENABLE_CORS` | Enable CORS middleware (default: `false`, not needed with rewrites) | No |
| `SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID` | Google OAuth client ID (read by Supabase via `supabase/config.toml`) | Only if using Google OAuth |
| `SUPABASE_AUTH_EXTERNAL_GOOGLE_SECRET` | Google OAuth client secret | Only if using Google OAuth |

## Security Features

- **CSRF Protection** -- `enforceSameOrigin` check on all mutation API routes (Origin-only in production; Host fallback dev-only)
- **JWT Verification** -- JWKS-based (recommended) or HS256 with no silent fallback. Concurrent-fetch lock and one-shot refresh on signature/kid mismatch handle key rotation.
- **MFA/TOTP** -- Fail-closed enforcement: MFA check errors `signOut()` the partial session before redirecting to login. The OAuth/confirm/callback POST routes all require AAL2 step-up.
- **Rate Limiting** -- slowapi on FastAPI sensitive endpoints; Redis-backed limiter on Next.js auth routes (login, register, forgot-password, change-password, magic-link, callback POST). Defaults to fail-closed when Redis is configured but unreachable.
- **Row-Level Security** -- RLS policies on all database tables. `audit_logs` is locked to `service_role` inserts only — authenticated users cannot forge entries.
- **Superadmin Protection** -- Live `auth.admin.getUserById()` check before any admin modification; stale `app_metadata` is never trusted.
- **httpOnly Cookie Sessions** -- Tokens are set as httpOnly cookies via `@supabase/ssr`, never exposed in response bodies.
- **Session Invalidation** -- Admin actions (ban, delete, password reset) revoke all target user sessions via GoTrue admin API.
- **Audit Trail** -- ban/unban/delete/reset-password/resend-verification/change-password all write to `audit_logs` via the service-role client.
- **OAuth Hardening** -- `next` redirect param is server-side allowlisted (no open redirect); client mirror throws on unsafe paths. Magic-link `emailRedirectTo` is derived from `NEXT_PUBLIC_SITE_URL` only (never the request Origin header). Magic-link route always returns the same generic message (no account enumeration).

## Useful URLs (Local Development)

| URL | Description |
|-----|-------------|
| http://localhost:3000 | Frontend application |
| http://localhost:3000/admin | Admin panel (requires super_admin role) |
| http://localhost:8000/docs | FastAPI Swagger documentation |
| http://localhost:8000/redoc | FastAPI ReDoc documentation |
| http://localhost:8000/health | Backend health check endpoint |
| http://localhost:56323 | Supabase Studio (database GUI) |
| http://localhost:56324 | Mailpit (email testing inbox) |

## Troubleshooting

### Supabase won't start

Make sure Docker is running and no other services are using ports 56321-56327:

```bash
npx supabase status
```

If you need to start fresh:

```bash
npx supabase stop
npx supabase start
npx supabase db reset --local
```

### Backend can't connect to database

1. Verify Supabase is running: `npx supabase status`
2. Check `DATABASE_URL` in `backend/.env` points to port 56322
3. Test the connection directly: `psql "postgresql://postgres:postgres@127.0.0.1:56322/postgres"`

### JWT validation errors

1. Verify `JWT_SECRET` in `backend/.env` matches your Supabase project's JWT secret
2. Check token expiration (default: 1 hour, configurable in `supabase/config.toml`)
3. Try setting `USE_JWKS=false` for HS256 fallback during debugging

### Frontend API calls return 502

The FastAPI backend must be running on port 8000. Next.js rewrites `/api/v1/*` requests to `http://127.0.0.1:8000/api/v1/*` (configured in `next.config.ts`).

### Admin panel shows "Access Denied"

Your user needs the `super_admin` role. Promote your user using the SQL commands in the "First User Setup" section, then log out and log back in to refresh the JWT token with updated permissions.

## License

MIT
