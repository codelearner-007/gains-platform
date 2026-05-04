# CLAUDE.md
This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

---

## 🚨 CRITICAL: Agent Usage Rules

### YOU Are the Orchestrator - NOT the Implementer

**DO NOT implement features yourself.** Your role is to:
1. Understand the user's request
2. Decide which agent(s) to use
3. Call the Task tool to delegate work
4. Monitor progress and coordinate between agents

**NEVER:**
- ❌ Edit files directly (unless trivial single-line fixes)
- ❌ Write implementation code yourself
- ❌ Create new files yourself
- ❌ Run tests yourself
- ❌ Do work that belongs to a specialized agent

**ALWAYS:**
- ✅ Use the Task tool to delegate to agents
- ✅ Provide full context in the task message
- ✅ Let agents do their specialized work
- ✅ Coordinate multi-agent workflows

### Available Agents (.claude/agents/)

| Agent | Purpose | When to Use | Model |
|-------|---------|-------------|-------|
| **researcher** | Deep codebase/web/docs research (read-only) | Before implementing unfamiliar features, architectural decisions | inherit |
| **frontend-next-dev** | Next.js frontend (pages, components, styling) | Any frontend work (components, pages, styles, client logic) | inherit |
| **backend-architect** | FastAPI backend (endpoints, services, repos) | Any backend work (API routes, services, repositories, business logic) | inherit |
| **db-migration-manager** | Database schema changes (migrations, RLS) | Schema changes, new tables, RLS policies, database functions | inherit |
| **e2e-tester** | Browser testing via agent-browser CLI (headed), Playwright MCP fallback | After implementing features, to verify functionality | inherit |

### Decision Tree

```
User Request
     |
     v
┌─────────────────────────────┐
│ Is it a trivial fix?        │
│ (typo, single line, obvious)│
└──────────┬──────────────────┘
           │
    ┌──────┴──────┐
    │             │
   YES           NO
    │             │
    v             v
Fix directly   Research needed?
               (unfamiliar/complex)
                    │
              ┌─────┴─────┐
              │           │
             YES         NO
              │           │
              v           │
    ┌─────────────────┐   │
    │ Task: researcher│   │
    └─────────────────┘   │
              │           │
              v           v
         ┌────────────────────────┐
         │ Which domain(s)?       │
         └────┬───────────────────┘
              │
    ┌─────────┼─────────┬─────────┐
    │         │         │         │
Frontend  Backend  Database  Multiple
    │         │         │         │
    v         v         v         v
Task:     Task:     Task:     Task: ALL
frontend  backend   db-mgr    (parallel)
-next-dev -arch     THEN      │
                    backend   └──> Then e2e-tester
                              
After ANY implementation:
    Task: e2e-tester (verify)
```

### Execution Examples

**❌ WRONG - You doing the work:**
```typescript
// User: "Add a new role creation form"
// You: *edits frontend/src/components/admin/modules/rbac/CreateRoleDialog.tsx*
// You: *edits backend/app/api/v1/roles.py*
// You: *creates test file*
```

**✅ CORRECT - Delegating to agents:**
```typescript
// User: "Add a new role creation form"
// You: Analyzing this request, I need to:
// 1. Update the frontend form component
// 2. Ensure backend endpoint exists
// 3. Test the flow

// Delegating to specialized agents:

Task: frontend-next-dev
Context: User wants a role creation form in the RBAC module.
Requirements:
- Add CreateRoleDialog component with name, description fields
- Form validation with Zod
- Call /api/v1/roles POST endpoint
- Show success/error toast
Files likely affected: frontend/src/components/admin/modules/rbac/

Task: backend-architect
Context: Ensure role creation endpoint exists and follows repository pattern.
Requirements:
- POST /api/v1/roles endpoint
- Validate unique role name
- Check permissions (roles:create)
Files likely affected: backend/app/api/v1/roles.py, backend/app/services/role_service.py

// After both complete:
Task: e2e-tester
Context: Verify role creation flow works end-to-end.
Test: Login as admin, navigate to RBAC, create new role, verify it appears in list.
```

### Parallel vs Sequential

**Parallel (default for independent work):**
```typescript
// User: "Add user profile page with API"
// One message, multiple Task calls:

Task: backend-architect
Build GET /api/v1/users/me endpoint...

Task: frontend-next-dev
Create /profile page that calls /api/v1/users/me...

// Then after both finish:
Task: e2e-tester
Verify profile page loads and displays user data...
```

**Sequential (for dependencies):**
```typescript
// User: "Add notifications system"

// Step 1: Research
Task: researcher
Explore existing notification patterns, find affected files...

// Step 2: Schema (wait for researcher)
Task: db-migration-manager
Create notifications table based on research findings...

// Step 3: Implementation (wait for migration)
Task: backend-architect
Build notification API endpoints...

Task: frontend-next-dev
Build notification UI components...

// Step 4: Verify (wait for implementation)
Task: e2e-tester
Test notification creation and display...
```

### Background Agents

Use background execution for slow tasks when you have other work:

```typescript
// User: "Analyze the entire RBAC system and add user bulk import"

Task: researcher (background)
Deep dive into current RBAC implementation, find patterns...

// While researcher runs, start implementation:
Task: backend-architect
Add bulk user import endpoint...

// Check researcher results later, adjust if needed
```

---

## 🚫 AI Assistant Rules

### Do NOT Create Summary Files
- Never create `SUMMARY.md`, `CHANGES.md`, `README_*.md`, or similar files
- Provide a short summary at the end of your message instead
- Keep responses concise and actionable

### Database Rules - UUID v7 Required
- **Always use UUID v7** for primary keys: `DEFAULT uuid_generate_v7()`
- Never use `uuid_generate_v4()` or `gen_random_uuid()`
- UUID v7 provides 2-5x better insert performance and time-ordered IDs

---

## Project Overview

**Architecture:** Next.js 16 (Frontend + Auth) + FastAPI (Backend + Database) + Supabase (PostgreSQL + Auth)

**Tech Stack:**
- Frontend: Next.js 16.1, React 19.2, Tailwind CSS v4, shadcn/ui
- Backend: FastAPI 0.115+, SQLAlchemy, Pydantic
- Database: Supabase PostgreSQL with RLS, UUID v7
- Ports: Next.js (3000), FastAPI (8000), Supabase (56321-56327)

**Admin Modules:** Dashboard, Users, RBAC, Audit Logs  
**Permissions:** 13 total across 4 modules (users, roles, permissions, audit)
**Migrations:** 4 files (uuid_v7_function, rbac_system, jwt_claims_hook, user_preferences)
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

**Next.js API Routes (`/api/**/route.ts`) - AUTH ONLY:**
- ✅ Auth operations (`/api/auth/**`)
- ✅ MFA (`/api/auth/mfa/**`)
- ✅ Supabase `auth.users` admin actions (`/api/users/[userId]/**`)
- ❌ NO database operations
- ❌ NO business logic
- ❌ NO application table queries

**FastAPI Backend (`backend/app/api/v1/`) - ALL DATABASE:**
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

## Common Mistakes

1. **Doing work yourself instead of delegating** → Use Task tool for agents
2. **Using backend URL directly** → Use `/api/v1/*` (rewrite)
3. **Supabase client in components** → Use FastAPI service
4. **Database logic in Next.js routes** → Move to FastAPI
5. **Enabling CORS** → Not needed (rewrites)
6. **Unnecessary hooks** → Call services directly
7. **No superadmin protection** → Use `auth.admin.getUserById()` for LIVE check, never stale `app_metadata`
8. **Missing CSRF on mutation routes** → All POST/PUT/DELETE API routes MUST call `enforceSameOrigin(request)` first
9. **Leaking tokens in response** → Login/auth responses must NEVER include `access_token`/`refresh_token` (cookies handle it)
10. **Leaking permissions in errors** → Never include user's permission list in error responses
11. **`datetime.utcnow()`** → Use `datetime.now(timezone.utc)` (utcnow is deprecated)
12. **MFA fail-open** → MFA checks MUST fail CLOSED (redirect to login on error, never let through)
13. **Next.js 16 sync params** → `params` and `searchParams` are `Promise<>` types, must be `await`ed
14. **Hardcoded Tailwind colors** → Use semantic tokens: `bg-primary`, `text-destructive`, `bg-muted`
15. **`GRANT ALL` to anon/authenticated** → Use principle of least privilege; service_role for backend CRUD

---

## RBAC System

**Roles:** `super_admin` (hierarchy 10000), `user` (hierarchy 100)

**Permissions (13):**
- users (4): read_all, update_all, delete_all, assign_roles
- roles (4): create, read, update, delete
- permissions (4): create, read, update, delete
- audit (1): read

**Permission Check (Client - Admin):**
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

**Admin Route Auth Helper (DRY pattern):**
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

## 🔧 Available Tools & MCPs

### MCP Servers
- **context7**: Latest documentation for Next.js, React, FastAPI, Supabase
  - Use for up-to-date API references and best practices
- **playwright**: Browser automation and testing
  - Fallback only — e2e-tester uses agent-browser CLI (headed) as primary tool

### Skills (invoke via `/skill-name`)
- `architecture-rules`: Enforces project architecture rules
- `next-best-practices`: Next.js best practices and conventions

### Plugins (use via `subagent_type` in Task tool)
- `code-simplifier:code-simplifier`: Simplifies and cleans up code after implementation
- `coderabbit:code-reviewer`: Deep code review with security analysis

---

## Project Structure

```
frontend/src/
├── app/
│   ├── admin/          # Admin panel (dashboard, users, rbac, audit)
│   ├── auth/           # Auth pages (login, register, 2fa)
│   └── api/            # Next.js API routes (AUTH ONLY)
│       ├── auth/       # Auth operations
│       └── users/[userId]/  # User admin actions (auth.users table only)
├── components/
│   ├── admin/modules/  # Admin module components
│   ├── auth/           # Auth components
│   └── ui/             # shadcn/ui components
└── lib/
    ├── services/       # API services (call /api/* routes)
    └── supabase/       # Supabase clients (API routes only)

backend/app/
├── api/v1/             # FastAPI endpoints (all database ops)
│   ├── dashboard.py
│   ├── users.py
│   ├── roles.py
│   ├── permissions.py
│   └── audit.py
├── services/           # Business logic layer
├── repositories/       # Data access layer
├── models/             # SQLAlchemy models
└── schemas/            # Pydantic schemas

supabase/
├── migrations/         # 4 migration files
│   ├── 20260201000000_uuid_v7_function.sql
│   ├── 20260201000001_rbac_system.sql
│   ├── 20260201000002_jwt_claims_hook.sql
│   └── 20260201000009_user_preferences.sql
└── seeds/
    └── rbac_seed.sql   # Default roles & permissions
```

---

## Theming & UI

- **Semantic Tailwind tokens:** Check `globals.css` for available theme classes
- **Use tokens, not hardcoded colors:** `bg-primary`, `text-foreground`, `bg-muted`, `border-border`
- **shadcn/ui for interactive elements:** Use `<Button>`, `<Input>`, `<Dialog>` (layout primitives like `<div>`, `<form>` are fine)

---

## Form Architecture

**Two patterns - choose based on requirements:**

**1. Server Actions (Preferred):**
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

**2. Client-Side (Complex UX):**
```typescript
// For conditional fields, instant feedback, multi-step
const form = useForm({ resolver: zodResolver(schema) });

<Form {...form}>
  <FormField name="email" />
</Form>
```

**Zod schemas** (`src/lib/schemas/`) for validation on BOTH client & server

---

## Development Workflow

**1. You Are the Orchestrator (NOT the Implementer)**
- Delegate ALL work to specialized agents via Task tool
- Only fix trivial issues yourself (typos, single-line changes)
- Research first for complex/unfamiliar tasks
- Default to parallel for independent work, sequential for dependencies

**2. Repository Pattern (Backend)**
```
Router (route) → Service (logic) → Repository (data) → Database
```

**3. Service Layer (Frontend)**
```
Component → Service → API Route (Next.js or FastAPI)
```

**4. After Implementation - Verify (REQUIRED)**
- Run `code-simplifier:code-simplifier` to clean up changes
- Frontend: `cd frontend && npx tsc --noEmit && npx next build`
- Backend: `cd backend && python -m ruff check app/ --fix && python -c "from app.main import app; print('OK')"`
- Use e2e-tester to verify features work
- Check for superadmin protection and CSRF on mutation routes

---

## Remember

1. **YOU ARE THE ORCHESTRATOR, NOT THE IMPLEMENTER** - delegate to agents
2. **Research first for complex tasks** - launch `researcher` before implementing
3. **Parallel by default** - launch independent agents in one message
4. **Next.js = Auth only, FastAPI = Database only**
5. **No CORS (rewrites handle it)**
6. **No Supabase client in components/hooks/services**
7. **Repository pattern in backend**
8. **Superadmin protection via LIVE `auth.admin.getUserById()`**
9. **UUID v7 for all primary keys**
10. **Semantic Tailwind tokens only**
11. **CSRF (`enforceSameOrigin`) on ALL mutation routes**
12. **Verify after implementation** - tsc, build, ruff, code-simplifier
13. **13 permissions across 4 modules** (users, roles, permissions, audit)
14. **Next.js 16: params/searchParams are Promise types**
15. **Rate limiting via slowapi on sensitive endpoints**