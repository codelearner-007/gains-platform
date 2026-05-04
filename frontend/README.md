# Frontend -- Next.js 16

The frontend application built with Next.js 16.1, React 19, TypeScript, Tailwind CSS v4, and shadcn/ui.

## Setup

```bash
cp .env.example .env.local
npm install
npm run dev
```

The development server starts on http://localhost:3000.

## Architecture

- **Next.js 16.1** with App Router and React 19 Server Components
- **Tailwind CSS v4** with semantic design tokens (`bg-primary`, `text-foreground`, `bg-muted`)
- **shadcn/ui** for all interactive components (Button, Input, Dialog, Select, etc.)
- **next-themes** for dark mode with system-aware switching
- **Supabase SSR** for cookie-based authentication (httpOnly, no tokens in response body)
- **Zod** for client-side form validation (shared schemas in `lib/schemas/`)
- **react-hook-form** with `zodResolver` for all forms

## Key Rules

1. **Supabase client is only used in API routes and middleware** -- never in components, hooks, or service files.
2. **All database operations go through FastAPI** via the `/api/v1/*` rewrite (configured in `next.config.ts`). Never call `http://localhost:8000` directly.
3. **Use semantic Tailwind tokens** -- `bg-primary`, `text-foreground`, `bg-muted`, `border-border`, not hardcoded colors like `bg-blue-500`.
4. **Use shadcn/ui for interactive elements** -- `<Button>`, `<Input>`, `<Select>`, `<Dialog>`, not raw `<button>`, `<input>`, `<select>`.
5. **`params` and `searchParams` are Promise types in Next.js 16** -- they must be `await`ed in page and layout components.
6. **Pages are thin** -- extract UI into component files, keep page files to 3-5 lines.
7. **Permission checks in admin UI** -- use `useAdminClaims()` and `hasPermission()` to conditionally render elements.

## Structure

```
src/
|-- app/
|   |-- page.tsx               # Landing page
|   |-- admin/                 # Admin panel
|   |   |-- [module]/page.tsx  # Dynamic admin module (dashboard, users, rbac, audit)
|   |   |-- layout.tsx         # Admin layout with AdminClaimsProvider
|   |-- app/                   # Authenticated app pages
|   |   |-- page.tsx           # App dashboard
|   |   |-- user-settings/     # Profile and security settings
|   |-- auth/                  # Auth pages
|   |   |-- login/             # Login page
|   |   |-- register/          # Register page
|   |   |-- forgot-password/   # Password reset request
|   |   |-- reset-password/    # Password reset form
|   |   |-- verify-email/      # Email verification
|   |   |-- 2fa/               # MFA/TOTP verification
|   |-- api/                   # Next.js API routes (auth only)
|   |   |-- auth/              # Auth operations (login, register, logout, MFA, etc.)
|   |   |-- users/[userId]/    # User admin actions (ban, unban, delete, reset-password)
|
|-- components/
|   |-- admin/                 # Admin panel components
|   |   |-- modules/           # Module-specific UI (rbac, users, audit)
|   |   |-- AdminClaimsContext # JWT claims provider for admin permission checks
|   |-- app/                   # App page components (DashboardPage, UserSettingsPage)
|   |-- auth/                  # SSOButtons, MagicLinkForm, AuthMethodsDivider, MFA pages
|   |-- common/                # Shared components (SiteNav, SiteFooter, AppLayout, AccessDenied)
|   |-- forms/                 # Form components
|   |   |-- auth/              # Auth forms (LoginForm, RegisterForm, etc.)
|   |   |-- user/              # User forms (ProfileForm, ChangePasswordForm, AvatarUpload)
|   |-- ui/                    # shadcn/ui primitives
|
|-- lib/
|   |-- services/              # API service layer (all fetch calls)
|   |   |-- api-client.ts      # Base API client (handles JSON, errors)
|   |   |-- auth.service.ts    # Auth operations (/api/auth/*)
|   |   |-- user.service.ts    # User profile and password (/api/auth/*, /api/v1/profile)
|   |   |-- rbac.service.ts    # RBAC operations (/api/v1/roles, /api/v1/permissions)
|   |-- schemas/               # Zod validation schemas
|   |-- supabase/              # Supabase client factories (API routes only)
|   |-- context/               # React context (GlobalContext for user state)
|   |-- utils/                 # Helper functions (rbac, admin-auth, cn)
```

## Environment Variables

| Variable | Description |
|----------|-------------|
| `NEXT_PUBLIC_SUPABASE_URL` | Supabase API URL (port 56321 locally) |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Supabase anonymous key |
| `PRIVATE_SUPABASE_SERVICE_KEY` | Supabase service role key (server-side only) |
| `NEXT_PUBLIC_PRODUCTNAME` | Application display name |
| `NEXT_PUBLIC_SITE_URL` | App URL — used to build OAuth and magic-link redirect targets (must be set in production) |
| `NEXT_PUBLIC_SSO_PROVIDERS` | Comma-separated list of enabled SSO providers (default: `google`; supports `google`, `github`) |
| `FRONTEND_REDIS_URL` | Redis URL for Next.js auth-route rate limiting (omit to disable in dev) |
| `FRONTEND_RATE_LIMIT_FAIL_OPEN` | When Redis is unreachable: `true` (allow) or `false` (default — fail-closed 503) |

## API Routing

Next.js rewrites `/api/v1/*` requests to the FastAPI backend:

```typescript
// next.config.ts
{
  source: "/api/v1/:path*",
  destination: `${process.env.NEXT_PUBLIC_API_URL || "http://127.0.0.1:8000"}/api/v1/:path*`
}
```

- Auth calls go to Next.js API routes: `fetch('/api/auth/login')`
- Database calls go through the rewrite: `fetch('/api/v1/roles')`

## Verification

```bash
# Type checking
npx tsc --noEmit

# Linting
npm run lint

# Production build (type checks + build)
npm run build
```

## Available Scripts

| Script | Description |
|--------|-------------|
| `npm run dev` | Start development server (port 3000) |
| `npm run build` | Production build with type checking |
| `npm run start` | Start production server |
| `npm run lint` | Run ESLint |
| `npm run test` | Run Vitest unit tests |
