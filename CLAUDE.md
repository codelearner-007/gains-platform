# CLAUDE.md

Guidance for Claude Code (claude.ai/code) when working in this repository.

This file has two halves:

1. **Working agreement** — how Claude should plan, execute, verify, and communicate (applies to every task).
2. **Gains Platform business rules** — architecture, RBAC, mistakes to avoid, project layout (applies to code in this repo).

When the two ever appear to conflict, the project rules in half 2 win for *what* the code must look like; the working agreement in half 1 governs *how* Claude works.

---

# Part 1 — Working Agreement

## Core Principles

1. **Think before code** — explore intent, write a plan, then implement.
2. **Evidence before assertions** — never claim "done", "fixed", or "passing" without running the verification command and reading the output.
3. **Do exactly what was asked** — no scope creep, no surprise refactors, no extra files.
4. **Edit > create** — prefer modifying existing files. Don't create docs unless asked.
5. **Root cause > shortcut** — fix the bug, don't bypass the check (`--no-verify`, `--force`, mocking around the failure).
6. **Confirm before destructive ops** — anything irreversible or affecting shared state: ask first.
7. **Delegate research** — for any exploration spanning more than 3 lookups, spawn a subagent (`Explore`, `general-purpose`, or `Plan`) instead of polluting main context.

---

## When to Run the Full Workflow vs. Skip Steps

**Run the FULL workflow** for:
- New features or user-facing capabilities
- Bug fixes with non-trivial root cause
- Refactors touching 3+ files
- Anything touching auth, payments, DB schema, or security boundaries
- Anything the user calls "important", "ship-ready", or "PR-ready"

**SKIP to minimum (steps 4 + 9 + 12 only)** for:
- Single-line typo / comment / rename
- User follow-up that adjusts work already verified this session ("change the color", "rename that var", "also do X to the same file")
- Pure formatting, log message, or copy tweaks
- Reverting a change made minutes ago
- Documentation edits the user explicitly asked for

Don't run it after every cosmetic change.

---

## Standard Workflow

If a referenced skill is unavailable, execute the **Fallback** inline.

### 1. Understand intent — brainstorming
- **Skill**: `superpowers:brainstorming`
- **Fallback**: 2–3 clarifying questions, restate goal, list constraints + success criteria.

### 2. Locate code — delegated exploration
- **Agents**: `Explore` for 1–3 targeted lookups; `Agent(general-purpose)` or `Agent(Explore)` "very thorough" for broad mapping.
- **Rule**: Delegate when search spans 3+ queries or unfamiliar territory. Keep main context clean.
- **Fallback**: `grep` / `rg` / `find` / `Read` with `file:line` notes.

### 3. Plan the change — writing-plans
- **Skill**: `superpowers:writing-plans` or `Agent(Plan)`.
- **Fallback**: Numbered list of steps, critical files, risks, rollback path. Get user approval before writing code on anything non-trivial.

### 4. Implement with discipline — test-driven-development
- **Skill**: `superpowers:test-driven-development`
- **Fallback**: Failing test → minimum code → refactor. No test framework? Write a tiny repro script.
- **Rule**: Trust framework guarantees. No "just in case" handlers. No half-finished stubs.

### 5. Debug when stuck — systematic-debugging
- **Skill**: `superpowers:systematic-debugging`
- **Fallback**: Reproduce → isolate → bisect. Form hypothesis, predict output, run, compare. Instrument, don't guess.

### 6. Parallelize independent work — dispatching-parallel-agents
- **Skill**: `superpowers:dispatching-parallel-agents`
- **Fallback**: Multiple `Agent` calls in one message when tasks share no state.

### 7. Isolate risky work — using-git-worktrees
- **Skill**: `superpowers:using-git-worktrees`
- **Fallback**: `git worktree add ../wt-feature feature-branch`.

### 8. Simplify before commit
- **Agent**: `code-simplifier:code-simplifier` or skill `simplify`.
- **Fallback**: Re-read diff. Delete dead code, redundant comments, premature abstractions. Three similar lines beats a bad abstraction.

### 9. Verify before claiming done — verification-before-completion
- **Skill**: `superpowers:verification-before-completion`
- **Fallback**: Run the actual commands. Paste real output. Required gates:
  - Type check passes — `cd frontend && npx tsc --noEmit`
  - Lint passes — `cd backend && python -m ruff check app/`
  - Affected tests pass — `vitest`, `pytest`, etc.
  - For UI: dev server started, feature exercised in browser, no console errors

### 10. Self-review the diff
- **Agent**: `coderabbit:code-reviewer` or skill `code-review:code-review`.
- **Fallback**: `git diff` against base. Read every changed line. Check for: secrets, debug logs, TODOs, scope creep, untested branches.

### 11. Security pass (conditional — see "When to Skip" above)
- **Skill**: `security-review`
- **Fallback**: Auth on every endpoint, tenant/user scoping enforced, no SQL via string concat, no secrets in code, no PII in logs, inputs validated at boundaries.

### 12. Commit with conventional standards

Standard Conventional Commits — no plugin required.

```
<type>(<scope>): <imperative summary, ≤72 chars>

<body — optional, explains WHY>
```

Types:
- `feat` — new user-facing capability
- `fix` — bug fix
- `refactor` — internal change, no behavior diff
- `perf` — performance improvement
- `test` — tests only
- `docs` — docs only
- `chore` — build, tooling, deps
- `ci` — CI config
- `style` — formatting only
- `revert` — reverts prior commit

Rules:
- Imperative mood (`add`, not `added`/`adds`)
- Lowercase summary
- No trailing period
- No `Co-Authored-By`, no robot emojis, no "Generated with Claude"
- Breaking change: `feat(api)!: …` + `BREAKING CHANGE:` footer
- Body explains WHY when summary alone leaves doubt

Examples:
- `feat(auth): add magic-link login`
- `fix(cart): prevent negative-quantity submit`
- `refactor(api): extract pricing into service module`
- `perf(search): cache product index for 60s`
- `chore(deps): bump zod to 3.23`

### 13. Acting on review feedback
- **Skill**: `superpowers:receiving-code-review` — verify each comment before applying.
- **Fallback**: For every reviewer comment: confirm with test/grep that the claim holds; push back on incorrect ones; never blind-apply.

---

## Agent Quick-Reference

| Need | Tool |
|---|---|
| Find symbol / file (1–3 queries) | `Explore` agent or `grep` |
| Map large area of codebase | `Agent(Explore)` "very thorough" |
| Open-ended multi-step research | `Agent(general-purpose)` |
| Architect a plan | `Agent(Plan)` |
| Clean up code before commit | `code-simplifier:code-simplifier` |
| Review diff | `coderabbit:code-reviewer` |
| Security audit | `security-review` skill |

Delegate to subagents whenever research or exploration would consume more than a handful of main-context tool calls. Independent subagent work → run in parallel.

---

## What NOT to Do

- ❌ Skip the plan on non-trivial work because "it's simple".
- ❌ Add error handling for impossible states.
- ❌ Write comments that restate code. Only document non-obvious WHY.
- ❌ Leave half-finished implementations, dead branches, stub functions.
- ❌ Use `--no-verify`, `--force`, or destructive git ops without explicit user request.
- ❌ Commit `.env`, credentials, large binaries, anything in `.gitignore`.
- ❌ Claim success without running the verification command.
- ❌ Create `README.md` / `SUMMARY.md` / `CHANGES.md` or any other markdown files unless the user explicitly asked for them.
- ❌ Run security review on cosmetic changes.

---

## Communication Style

- Default short. Clear sentence beats clear paragraph.
- State results, not internal deliberation.
- Before each tool batch: one sentence on what you're doing.
- End of turn: 1–2 sentences. What changed, what's next.
- Reference code as `path/file.ext:line`.
- Unsure → ask. Confident → act.

---

# Part 2 — Gains Platform Business Rules

## Project Overview

**Architecture:** Next.js 16 (Frontend + Auth) + FastAPI (Backend + Database) + Supabase (PostgreSQL + Auth)

**Tech Stack:**
- Frontend: Next.js 16.1, React 19.2, Tailwind CSS v4, shadcn/ui
- Backend: FastAPI 0.115+, SQLAlchemy, Pydantic
- Database: Supabase PostgreSQL with RLS, UUID v7
- Ports: Next.js (3000), FastAPI (8000), Supabase (56321-56327)

**Admin Modules:** Dashboard, Users, RBAC, Audit Logs
**Permissions:** 13 total across 4 modules (users, roles, permissions, audit)
**Auth methods:** email/password, Google OAuth (PKCE), email magic link, MFA/TOTP step-up

---

## 🚨 CRITICAL Architecture Rules

### Request Routing

**Next.js rewrites `/api/v1/*` to FastAPI automatically:**
```typescript
// next.config.ts
source: "/api/v1/:path*" → destination: "http://127.0.0.1:8000/api/v1/:path*"
```

**This means:**
- Frontend calls `/api/v1/users` (relative path)
- Next.js proxies to FastAPI (appears same-origin)
- **NO CORS needed**
- **NEVER use `http://localhost:8000` in frontend code**

### What Goes Where

**Next.js API Routes (`/api/**/route.ts`) — AUTH ONLY:**
- ✅ Auth operations (`/api/auth/**`)
- ✅ MFA (`/api/auth/mfa/**`)
- ✅ Supabase `auth.users` admin actions (`/api/users/[userId]/**`)
- ❌ NO database operations
- ❌ NO business logic
- ❌ NO application table queries

**FastAPI Backend (`backend/app/api/v1/`) — ALL DATABASE:**
- ✅ ALL database operations
- ✅ ALL business logic
- ✅ Repository pattern: Router → Service → Repository → Database
- ❌ NO auth operations (use Next.js)

### Supabase Client Usage

**NEVER import Supabase client in:**
- ❌ Components (`frontend/src/components/**`)
- ❌ Hooks (`frontend/src/hooks/**`)
- ❌ Services (`frontend/src/lib/services/**`)

**ONLY use Supabase client in:**
- ✅ Auth API routes (`/api/auth/**/route.ts`)
- ✅ User admin routes (`/api/users/[userId]/**/route.ts`)
- ✅ Middleware (`/middleware.ts`)
- ✅ OAuth redirect (client-side only)

### Quick Reference

```typescript
// ✅ Auth → Next.js
fetch('/api/auth/login', { method: 'POST', ... });

// ✅ Database → FastAPI (via rewrite)
fetch('/api/v1/roles', { method: 'GET', ... });

// ❌ NEVER: Direct backend URL
fetch('http://localhost:8000/api/v1/roles'); // CORS issues

// ❌ NEVER: Supabase in service
const supabase = createBrowserClient();
await supabase.from('roles').select('*'); // Use FastAPI
```

```python
# ✅ Repository pattern
@router.get("/")
async def list_roles(service: RoleService = Depends()):
    return await service.list_all()

# ❌ Direct DB access in router
@router.get("/")
async def list_roles(db: AsyncSession = Depends()):
    return await db.execute(select(Role))
```

---

## Database Rules — UUID v7 Required

- **Always use UUID v7** for primary keys: `DEFAULT uuid_generate_v7()`
- Never use `uuid_generate_v4()` or `gen_random_uuid()`
- UUID v7 provides 2-5× better insert performance and time-ordered IDs

---

## Common Mistakes

1. **Using backend URL directly** → Use `/api/v1/*` (rewrite handles it)
2. **Supabase client in components** → Use FastAPI service
3. **Database logic in Next.js routes** → Move to FastAPI
4. **Enabling CORS** → Not needed (rewrites)
5. **Unnecessary hooks** → Call services directly
6. **No superadmin protection** → Use `auth.admin.getUserById()` for LIVE check, never stale `app_metadata`
7. **Missing CSRF on mutation routes** → All POST/PUT/DELETE API routes MUST call `enforceSameOrigin(request)` first
8. **Leaking tokens in response** → Login/auth responses must NEVER include `access_token`/`refresh_token` (cookies handle it)
9. **Leaking permissions in errors** → Never include the user's permission list in error responses
10. **`datetime.utcnow()`** → Use `datetime.now(timezone.utc)` (utcnow is deprecated)
11. **MFA fail-open** → MFA checks MUST fail CLOSED (redirect to login on error, never let through)
12. **Next.js 16 sync params** → `params` and `searchParams` are `Promise<>` types, must be `await`ed
13. **Hardcoded Tailwind colors** → Use semantic tokens: `bg-primary`, `text-destructive`, `bg-muted`
14. **`GRANT ALL` to anon/authenticated** → Use principle of least privilege; service_role for backend CRUD

---

## RBAC System

**Roles:** `super_admin` (hierarchy 10000), `user` (hierarchy 100)

**Permissions (13):**
- users (4): `read_all`, `update_all`, `delete_all`, `assign_roles`
- roles (4): `create`, `read`, `update`, `delete`
- permissions (4): `create`, `read`, `update`, `delete`
- audit (1): `read`

**Permission Check (Client — Admin):**
```typescript
import { useAdminClaims } from '@/components/admin/AdminClaimsContext';
import { hasPermission } from '@/lib/utils/rbac';

const claims = useAdminClaims();
if (!hasPermission(claims.permissions, 'users:update_all')) {
  return <div>Access Denied</div>;
}
```

**Superadmin Protection (API Routes):**
```typescript
// ALWAYS fetch LIVE data for the target user, never trust stale app_metadata
const { data: targetUser } = await adminClient.auth.admin.getUserById(userId);
if (targetUser?.user?.app_metadata?.user_role === 'super_admin') {
  return NextResponse.json({ error: 'Superadmin users cannot be modified' }, { status: 403 });
}
```

**Admin Route Auth Helper (DRY):**
```typescript
// Use authorizeAdminAction() from lib/utils/admin-auth.ts for all admin mutation routes
const auth = await authorizeAdminAction(request, userId, 'users:update_all');
if (auth instanceof NextResponse) return auth;
// auth.adminClient and auth.userId are available
```

**Promote User to Super Admin:**
```bash
psql "postgresql://postgres:postgres@127.0.0.1:56322/postgres"
```
```sql
SELECT id, email FROM auth.users;

UPDATE user_roles
SET role_id = (SELECT id FROM roles WHERE name = 'super_admin')
WHERE user_id = 'user-uuid-here';
```
**Important:** User must refresh session after role change.

---

## Project Structure

```
frontend/src/
├── app/
│   ├── admin/          # Admin panel (dashboard, users, rbac, audit)
│   ├── app/            # Authenticated app (reports, settings)
│   ├── auth/           # Auth pages (login, register, 2fa)
│   └── api/            # Next.js API routes (AUTH ONLY)
│       ├── auth/       # Auth operations
│       └── users/[userId]/  # User admin actions (auth.users table only)
├── components/
│   ├── admin/modules/  # Admin module components
│   ├── app/modules/    # App-side feature modules (reports, etc.)
│   ├── auth/           # Auth components
│   └── ui/             # shadcn/ui components
└── lib/
    ├── services/       # API services (call /api/* routes)
    ├── reports/        # Report-specific helpers, types, filters
    └── supabase/       # Supabase clients (API routes only)

backend/app/
├── api/v1/             # FastAPI endpoints (all database ops)
├── services/           # Business logic layer
├── repositories/       # Data access layer (SQLAlchemy queries)
├── models/             # SQLAlchemy models
├── schemas/            # Pydantic schemas
├── jobs/               # Ingestion / pipeline jobs
└── transformations/    # SQL transformations (staging → dims → facts → cubes)

supabase/
├── migrations/         # Migration files (applied in order)
└── seeds/              # Seed data (roles, permissions, school config, standards)

data/                   # Source CSV exports + decoded PBIX reference
docs/                   # Internal documentation
```

---

## Theming & UI

- **Semantic Tailwind tokens:** check `globals.css` for available theme classes
- **Use tokens, not hardcoded colors:** `bg-primary`, `text-foreground`, `bg-muted`, `border-border`
- **Performance color tokens** (reports): `PERF_PINK` (<70%), `PERF_YELLOW` (70–80%), `PERF_GREEN` (≥80%), `INCORRECT_GREY`, `HEADER_BAR_BG`, `LAYOUT_BORDER` — all in `lib/reports/colors.ts`. Do not redefine.
- **shadcn/ui for interactive elements:** use `<Button>`, `<Input>`, `<Dialog>` (layout primitives like `<div>`, `<form>` are fine)

---

## Form Architecture

**Two patterns — choose based on requirements:**

**1. Server Actions (preferred):**
```typescript
// app/actions/user.ts
'use server';
export async function createUser(formData: FormData) {
  const data = schema.parse(Object.fromEntries(formData));
  // Process...
}

// Component
<form action={createUser}>
  <input name="email" />
  <button>Submit</button>
</form>
```

**2. Client-Side (complex UX):**
```typescript
// For conditional fields, instant feedback, multi-step
const form = useForm({ resolver: zodResolver(schema) });

<Form {...form}>
  <FormField name="email" />
</Form>
```

**Zod schemas** (`src/lib/schemas/`) for validation on BOTH client & server.

---

## Backend Verification Commands

After backend changes:
```bash
cd backend && ./venv/bin/python -m ruff check app/ --fix
cd backend && ./venv/bin/python -c "from app.main import app; print('OK')"
```

After frontend changes:
```bash
cd frontend && npx tsc --noEmit
cd frontend && npx vitest run             # affected unit tests
cd frontend && npx next build              # only when shipping
```

For UI changes: start `npm run dev`, exercise in browser, confirm zero console errors.

---

## Repository / Service Pattern

**Backend:**
```
Router (HTTP) → Service (logic) → Repository (data) → Database
```

**Frontend:**
```
Component → Service (lib/services) → API route (Next.js or FastAPI via /api/v1)
```

---

## Quick Sanity Checklist

1. Next.js = auth only. FastAPI = database only.
2. No CORS (rewrites handle it).
3. No Supabase client in components/hooks/services.
4. Repository pattern in backend.
5. Superadmin protection via LIVE `auth.admin.getUserById()`.
6. UUID v7 for all primary keys.
7. Semantic Tailwind tokens only.
8. CSRF (`enforceSameOrigin`) on ALL mutation routes.
9. `params` / `searchParams` are `Promise<>` in Next.js 16 — must be `await`ed.
10. Rate limiting via slowapi on sensitive backend endpoints.
