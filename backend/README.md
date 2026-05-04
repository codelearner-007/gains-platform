# Backend -- FastAPI

Production-ready FastAPI backend for the Next.js + Supabase SaaS starter template.

## Features

- **JWT Authentication** -- JWKS-based validation (recommended) with HS256 fallback
- **RBAC Authorization** -- Dynamic permission guards via dependency injection
- **Async Database** -- SQLAlchemy 2.0 with asyncpg and connection pooling
- **4-Layer Architecture** -- Routers > Services > Repositories > Models
- **Rate Limiting** -- slowapi on auth and sensitive endpoints
- **Structured Logging** -- JSON logging with request ID tracking
- **Auto-generated Docs** -- OpenAPI/Swagger UI at `/docs`, ReDoc at `/redoc`

## Setup

```bash
cd backend
cp .env.example .env
python -m venv venv

# Windows
venv\Scripts\activate

# macOS / Linux
source venv/bin/activate

pip install -r requirements.txt
```

Start the development server:

```bash
uvicorn app.main:app --reload --port 8000
```

Verify the installation:

- Health check: http://localhost:8000/health
- Swagger docs: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API Endpoints

All endpoints are prefixed with `/api/v1`. The frontend accesses them via `/api/v1/*`, which Next.js rewrites to this backend.

### Authentication

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/auth/me` | Authenticated | Get current user info and JWT claims |

### Profile

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/profile` | Authenticated | Get current user's profile (auto-creates if missing) |
| PATCH | `/profile` | Authenticated | Update current user's profile |

### Users (Admin)

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/users/stats` | `users:read_all` | Get user statistics |
| GET | `/users/with-roles` | `users:read_all` | List users with roles (paginated, filterable) |

### User Roles (Admin)

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/users/{user_id}/roles` | Own or `users:read_all` | List roles assigned to a user |
| POST | `/users/{user_id}/roles` | `users:assign_roles` | Assign a role to a user |
| DELETE | `/users/{user_id}/roles/{role_id}` | `users:assign_roles` | Remove a role from a user |

### Roles (RBAC Admin)

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/roles` | `roles:read` | List all roles |
| POST | `/roles` | `roles:create` | Create a new role |
| GET | `/roles/{id}` | `roles:read` | Get role details with permissions |
| PATCH | `/roles/{id}` | `roles:update` | Update a role |
| DELETE | `/roles/{id}` | `roles:delete` | Delete a role |
| GET | `/roles/{id}/permissions` | `roles:read` | Get permissions for a role |
| PUT | `/roles/{id}/permissions` | `roles:update` | Bulk replace role permissions |

### Permissions (RBAC Admin)

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/permissions` | `permissions:read` | List all permissions grouped by module |
| POST | `/permissions` | `permissions:create` | Create a new permission |
| DELETE | `/permissions/{id}` | `permissions:delete` | Delete a permission |

### Audit Logs

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/audit/logs` | `audit:read` | List audit logs (paginated, filterable by module, action, user, date range) |
| GET | `/audit/modules` | `audit:read` | List distinct module names from audit logs (for filter dropdown) |

### Dashboard

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/dashboard/stats` | `roles:read` | Get admin dashboard statistics |

### Sessions

| Method | Path | Permission | Description |
|--------|------|-----------|-------------|
| GET | `/sessions` | Authenticated | List the caller's active Supabase sessions |
| DELETE | `/sessions/{session_id}` | Authenticated | Revoke a specific session (cannot revoke the current one) |

## Architecture

### 4-Layer Design

```
Routers (app/api/v1/)        -- HTTP layer: request parsing, response formatting
    |
Services (app/services/)     -- Business logic, validation, orchestration
    |
Repositories (app/repositories/)  -- Data access, SQLAlchemy queries
    |
Models (app/models/)         -- SQLAlchemy ORM model definitions
```

- **Routers** handle HTTP concerns (request/response, status codes, dependency injection).
- **Services** contain business logic, enforce rules, and coordinate between repositories.
- **Repositories** are the only layer that touches the database.
- **Models** define the SQLAlchemy ORM mappings.

### Directory Structure

```
app/
|-- api/v1/            # API route handlers (thin HTTP layer)
|-- core/              # Config, security, dependencies, rate limiting, exceptions
|-- db/                # Database session management (async session factory)
|-- models/            # SQLAlchemy ORM models
|-- schemas/           # Pydantic schemas
|   |-- request/       # Request validation schemas
|   |-- response/      # Response serialization schemas
|-- services/          # Business logic (framework-free)
|-- repositories/      # Data access layer (SQLAlchemy queries)
|-- middleware/         # Custom middleware
```

## Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| `DATABASE_URL` | PostgreSQL connection string | Required |
| `SUPABASE_URL` | Supabase API URL | Required |
| `SUPABASE_ANON_KEY` | Supabase anonymous key | Required |
| `JWT_SECRET` | JWT signing secret (from Supabase) | Required |
| `USE_JWKS` | Use JWKS endpoint for JWT verification | `true` |
| `ENVIRONMENT` | `development` or `production` | `development` |
| `LOG_LEVEL` | Logging level | `INFO` |
| `DB_POOL_SIZE` | SQLAlchemy connection pool size | `10` |
| `DB_MAX_OVERFLOW` | Max overflow connections | `20` |
| `ENABLE_CORS` | Enable CORS middleware | `false` |
| `ALLOWED_ORIGINS` | Allowed CORS origins (JSON array) | `["http://localhost:3000"]` |

## JWT Verification

### JWKS-Based (Recommended)

Fetches public keys from Supabase's `/.well-known/jwks.json` endpoint. Supports RS256 and ES256 algorithms.

```bash
USE_JWKS=true
```

### HS256 Fallback

Uses the static JWT secret for validation. Suitable for development or when JWKS is unavailable.

```bash
USE_JWKS=false
JWT_SECRET=your-jwt-secret-here
```

There is no silent fallback between modes. If JWKS is enabled but the endpoint is unreachable, requests will fail with a 401 error.

### Token Structure

The JWT claims hook injects these custom claims into every Supabase token:

```json
{
  "sub": "user-uuid",
  "email": "user@example.com",
  "user_role": "super_admin",
  "hierarchy_level": 10000,
  "permissions": ["roles:create", "users:read_all", "..."]
}
```

## Permission Guards

Use dependency injection to enforce permissions on endpoints:

```python
from app.core.dependencies import require_permission

@router.post(
    "/roles",
    dependencies=[Depends(require_permission("roles:create"))],
)
async def create_role(...):
    ...
```

This returns a 403 error if the authenticated user lacks the required permission.

## Rate Limiting

Rate limiting is configured via slowapi with per-IP tracking:

- `/auth/me` -- 60 requests/minute
- User role assignment -- 30 requests/minute
- Other sensitive endpoints are rate-limited as needed

Rate limit exceeded responses return HTTP 429 with a `Retry-After` header.

## Error Handling

All endpoints return consistent JSON error responses:

```json
{
  "error": "Permission denied. Required: roles:create",
  "status_code": 403,
  "details": {
    "required_permission": "roles:create"
  }
}
```

Validation errors (422):

```json
{
  "error": "Validation failed",
  "status_code": 422,
  "details": [...]
}
```

In production (`ENVIRONMENT=production`), internal server errors do not include stack traces or error details.

## Code Quality

```bash
# Lint with ruff
ruff check app/

# Auto-fix lint issues
ruff check app/ --fix

# Format code
ruff format app/

# Verify the app imports correctly
python -c "from app.main import app; print('OK')"
```

## Database Migrations

This backend uses Supabase migrations (not Alembic). Migrations are stored in `supabase/migrations/`.

```bash
# Apply migrations to local Supabase
npx supabase migration up --local

# Reset local database (destroys data, re-runs migrations + seeds)
npx supabase db reset --local
```

## Deployment

### Docker

```bash
docker build -t fastapi-backend .
docker run -p 8000:8000 --env-file .env fastapi-backend
```

### Docker Compose (Full Stack)

From the project root:

```bash
docker-compose up --build
```

### Production Checklist

- [ ] Set `ENVIRONMENT=production`
- [ ] Set `LOG_LEVEL=WARNING`
- [ ] Use managed PostgreSQL connection string (Supabase Cloud)
- [ ] Enable JWKS (`USE_JWKS=true`)
- [ ] Keep `ENABLE_CORS=false` (Next.js rewrites handle same-origin)
- [ ] Configure reverse proxy (Nginx, Caddy) with HTTPS
- [ ] Set up monitoring and error tracking (Sentry, etc.)
- [ ] Verify rate limiting configuration for production traffic

## Troubleshooting

### Database connection failed

1. Check Supabase is running: `npx supabase status`
2. Verify `DATABASE_URL` in `.env` (port 56322 for local Supabase)
3. Test connection: `psql "postgresql://postgres:postgres@127.0.0.1:56322/postgres"`

### JWT validation failed

1. Verify `JWT_SECRET` matches your Supabase project's JWT secret
2. Check token expiration (default: 1 hour)
3. Try `USE_JWKS=false` for HS256 fallback during debugging

### Import errors

```bash
pip install -r requirements.txt --force-reinstall
```

### Rate limit errors during development

Rate limits are per-IP. If you hit limits during testing, wait for the window to expire or restart the server (rate limit state is in-memory).
