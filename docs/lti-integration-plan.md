# LTI 1.3 Integration Plan — Embedding the GAINS Dashboard in Schoology

**Status:** PLANNING ONLY. Nothing in this document is implemented. LTI remains gated OFF
(`LTI_ENABLED=False`, `backend/app/core/config.py:46`). Implementation begins only after
owner review and greenlight. See §12.

**Author's basis:** This plan verifies every claim below against the real current code (cited
`file:line`) and the prior research (`.planning/ingestion-lti/research/R1,R4,R6` +
`RESEARCH_BRIEF.md §4–6`). Where research and code diverged, code wins.

**Date:** 2026-07-22

---

## 1. Executive Summary & Goal

**Goal.** One GAINS LTI 1.3 tool, installed once per school in that school's Schoology
organization, lets a teacher or admin click a link inside Schoology and land — already
authenticated — in *their* school's GAINS dashboard, with strict per-school isolation and zero
cross-school data access. This is the direct, modern equivalent of the legacy EdvanceLearning
flow, where a Schoology LTI launch set a `__tenant` cookie and dropped the user into a Power BI
dashboard scoped by tenant + Power BI RLS (R1 §2.2, §4). The new platform replaces Power BI with
native GAINS reports and replaces ABP tenancy with Supabase per-school RLS.

**What is ALREADY built (reuse verbatim — do NOT rebuild):**

- **The full LTI 1.3 protocol handshake.** OIDC third-party login init, `id_token` form-POST
  validation (RS256 signature via the platform JWKS by `kid`, `iss`/`aud`/`exp`/`iat`/`sub`
  required, `nonce` match, `message_type == LtiResourceLinkRequest`), single-use state replay
  protection, IMS-role → school-role collapse, tenant resolution from the deployment binding, and
  provisioning of an `auth.users` row + `user_schools` membership.
  `backend/app/services/lti_service.py:89-366`, `backend/app/api/v1/lti.py:55-127`.
- **The four LTI tables.** `lti_registration`, `lti_deployment`, `lti_launch_session`,
  `lti_user_identity` — `supabase/migrations/20260601000020_lti.sql:14-62`.
- **The Schoology platform template + a working end-to-end mock launch harness.**
  `supabase/seeds/seed_lti.py` (`cmd_seed` at `:65-87`; `cmd_launch` mock at `:128-193`).
- **The entire per-school isolation stack** that a launch feeds into: `user_schools`
  membership (`supabase/migrations/20260601000000_user_schools.sql:18-53`), the JWT
  `custom_access_token_hook` that injects `school_ids`/`primary_school_id`/`is_super_admin`
  (`supabase/migrations/20260601000010_jwt_school_claims.sql:16-96`), the RLS
  `SET LOCAL ROLE authenticated` + `app.current_school_id` GUC middleware
  (`backend/app/middleware/rls.py:136-180`), and `tenant_iso_select` RLS policies on 35 per-tenant
  tables + `schools` (`supabase/migrations/20260507000090_rls_policies.sql:19-88`).
- **Session-mint templates to copy for the bridge.** OAuth PKCE callback that calls
  `exchangeCodeForSession` and sets `@supabase/ssr` cookies
  (`frontend/src/app/api/auth/callback/route.ts:40-59`); the magic-link confirm route that calls
  `verifyOtp({ type, token_hash })` and sets the session
  (`frontend/src/app/api/auth/confirm/route.ts:45-80`).

**What REMAINS to build (this plan's scope):**

1. **The session bridge (the blocker).** After `provision()`, the launch 302s to `/app/...` with
   a bare, forgeable `gains_lti_launch=<user_id>` cookie that **nothing on the Next.js side reads**
   (`lti.py:106-119`; grep of `frontend/src/app` for `gains_lti_launch`/`lti_uid` returns nothing).
   The Next middleware hard-requires a valid `supabase.auth.getUser()` for any `/app` route and
   bounces unauthenticated requests to `/auth/login`
   (`frontend/src/lib/supabase/middleware.ts:42-54`). So today **a real launch never reaches the
   dashboard.** The bridge must mint a real Supabase session for the provisioned user.
2. **A signed, single-use, short-TTL handoff token** replacing the bare-user-id cookie.
3. **Real Schoology registration data** per school (`client_id` + `deployment_id` from a district
   admin app install) seeded into `lti_registration` / `lti_deployment`.
4. **Iframe / CSP / cookie posture** for embedded launch under `*.schoology.com`.
5. **Automated tests** (none exist).
6. **Flip `LTI_ENABLED=True`** in the target env.
7. **(Optional, later)** LTI Advantage NRPS/AGS outbound service calls.

Phase 3 is **validate-seed-bridge, not greenfield.** The load-bearing gap is item 1.

---

## 2. Architecture — One Tool, N Schools

### 2.1 The isolation model rides on LTI identifiers

One GAINS tool serves every school. LTI 1.3's identifier hierarchy provides the isolation:

- **Registration** = one row per **`(issuer, client_id)`**. Holds the platform's auth/token/JWKS
  URLs and the tool's own signing keypair. `lti_registration`, `UNIQUE (issuer, client_id)`
  (`20260601000020_lti.sql:14-28`).
- **Deployment** = one row per **`deployment_id` within a registration**, and each `deployment_id`
  is bound to **exactly one GAINS `school_id`**. `lti_deployment`,
  `UNIQUE (registration_id, deployment_id)`, `school_id UUID REFERENCES schools`
  (`20260601000020_lti.sql:31-39`).
- **User identity** = one row per **`(registration_id, sub)`** → an `auth.users.id`.
  `lti_user_identity`, `UNIQUE (registration_id, sub)` (`20260601000020_lti.sql:54-62`).

### 2.2 The Schoology-specific constraint that shapes everything

Schoology is a single global cloud: its issuer is **constant across every district** —
`iss = https://schoology.schoology.com` (R4 §3.1; seeded at `seed_lti.py:45`). Therefore
**the issuer alone can NEVER identify a tenant.** Tenants MUST be disambiguated by
`client_id` (registration) + `deployment_id` (deployment). This is a hard design rule.

The current code respects it: `get_registration_by_issuer(issuer, client_id)` prefers the
`(iss, client_id)` pair (`lti_service.py:94-117`), and `_resolve_school(registration_id,
deployment_id)` resolves the school from the deployment binding (`lti_service.py:231-240`).

> **Caveat (verify before enabling):** `get_registration_by_issuer` has an **issuer-only
> fallback** when `client_id` is absent from the login-init request (`lti_service.py:107-115`).
> With multiple Schoology registrations sharing the same `iss`, that fallback would non-
> deterministically match the "first active" registration. Schoology **does** send `client_id`
> on the login-init request, so the fallback should never fire in practice — but Phase A should
> either require `client_id` at login when >1 Schoology registration exists, or drop the
> issuer-only branch, to remove the ambiguity entirely.

### 2.3 Trust boundary

The `id_token` is signed RS256 by Schoology and its `aud` MUST contain our `client_id`
(`lti_service.py:206-207`). A launch therefore **cannot forge a different tenant**: to be accepted
for school X, the token must be signed by Schoology AND its `deployment_id` claim must match a
deployment we bound to X. Isolation then rides on the resolved `school_id` through the RLS stack
(§4).

### 2.4 Text architecture / sequence diagram

```
  ┌──────────────────────┐         ┌─────────────────────────────────────────────┐
  │  Schoology (per       │         │                 GAINS                        │
  │  district / building) │         │                                              │
  │  iss = CONSTANT       │         │  FastAPI /api/v1/lti/*   Next.js /api/lti/*   │
  └──────────┬────────────┘         └──────────┬──────────────────────┬──────────┘
             │                                  │                       │
  (0) teacher clicks GAINS link in a course     │                       │
             │                                  │                       │
  (1) OIDC login init ─── GET/POST ────────────▶│ /api/v1/lti/login     │
      iss, login_hint, client_id,               │  resolve reg by       │
      target_link_uri, lti_message_hint         │  (iss, client_id);    │
             │                                  │  mint state+nonce;    │
             │◀── 302 to Schoology authorize ───│  persist launch sess  │
             │                                  │                       │
  (2) authorize (prompt=none) ─────────────────▶  [Schoology signs id_token]
             │                                  │                       │
  (3) form POST id_token + state ──────────────▶│ /api/v1/lti/launch    │
             │                                  │  consume state (1x);  │
             │                                  │  verify sig+claims;   │
             │                                  │  resolve deployment   │
             │                                  │   -> school_id;       │
             │                                  │  upsert auth.users +  │
             │                                  │   user_schools;       │
             │                                  │  ── TO BUILD ──▶      │
             │                                  │  mint signed 1-use    │
             │                                  │  handoff token,       │
             │                                  │  store server-side    │
             │                                  │       │               │
             │◀── 302 to /api/lti/bridge?ticket=… ──────┘               │
             │                                                          │
  (4) GET /api/lti/bridge?ticket=… ──────────────────────────────────▶ │  Next.js (auth only):
             │                                                          │   validate ticket (1x);
             │                                                          │   admin.generateLink
             │                                                          │    (magiclink) -> token_hash;
             │                                                          │   verifyOtp -> sets
             │                                                          │    @supabase/ssr cookies
             │◀── 302 to /app/...?school_id=<school_id> ─────────────────┘
             │
  (5) browser (now carrying sb-…-auth-token cookie) hits /app
       middleware getUser() OK ──▶ dashboard renders
       every /api/v1 report fetch carries the cookie + ?school_id
       -> get_db_with_rls sets ROLE authenticated + GUC -> RLS scopes rows to school_id
```

Steps (1)–(3) are **already implemented**. Step (4) and the token minting at the end of (3) are
**TO BUILD**. Step (5) is **already implemented** (the RLS/tenancy stack, §4).

---

## 3. LTI 1.3 Launch Flow — Step by Step (implemented vs. to-build)

Each step is tagged **[BUILT]** with `file:line` or **[TO BUILD]**.

### Step 1 — OIDC third-party login init — **[BUILT]**

- Schoology hits `GET`/`POST /api/v1/lti/login` with `iss`, `login_hint`, `client_id`,
  `target_link_uri`, `lti_message_hint`. Both verbs handled: `lti.py:55-84`.
- Resolve the registration by `(iss, client_id)`: `start_login` →
  `get_registration_by_issuer` (`lti_service.py:143`, `:94-117`). Unknown → `LtiError` → HTTP 400
  (`lti.py:50-51`).
- Generate single-use `state` + `nonce` (`secrets.token_urlsafe(32)`), persist an
  `lti_launch_session` row with a 300s TTL, commit (`lti_service.py:147-158`,
  `LAUNCH_TTL_SECONDS=300` `:48`).
- Redirect (302) to the platform authorize endpoint with
  `scope=openid, response_type=id_token, response_mode=form_post, prompt=none, client_id,
  redirect_uri=<tool /lti/launch>, login_hint, state, nonce` (+ `lti_message_hint` if present)
  (`lti_service.py:160-173`; redirect_uri from `_tool_launch_url` `lti.py:33-35`).

### Step 2 — id_token validation — **[BUILT]**

Schoology form-POSTs the signed `id_token` + `state` to `POST /api/v1/lti/launch`
(`lti.py:87-93`). `validate_launch` (`lti_service.py:218-228`):

- **Single-use state / replay** — `_consume_state` (`lti_service.py:176-197`): rejects unknown
  ("possible replay or expired"), already-consumed ("replay rejected"), or expired state; marks
  `consumed=TRUE` and commits. True one-shot use.
- **Signature + claims** — `_verify_id_token` (`lti_service.py:199-216`): fetch the signing key
  from the registration's `jwks_url` by `kid` (`PyJWKClient`, `:201`; rotation handled by refetch);
  `jwt.decode(..., algorithms=["RS256"], audience=client_id, issuer=registration.issuer,
  leeway=60, options={"require":["exp","iat","aud","iss","sub"]})` (`:202-209`); enforce `nonce`
  equality (`:211-212`) and `message_type == LtiResourceLinkRequest` (`:213-215`).
- Any `jwt.PyJWTError` → `LtiError` → HTTP 400 (`lti_service.py:226-227`, `lti.py:99-101`).

### Step 3 — provision (resolve tenant, upsert user + membership) — **[BUILT]**

`provision` (`lti_service.py:242-297`):

- Read LTI claims by URI: `deployment_id`, `roles`, `context`, `resource_link`; `email` falls back
  to `lti-{sub}@lti.local` (`lti_service.py:243-253`).
- **Tenant binding** — `_resolve_school(registration_id, deployment_id)` → `lti_deployment.school_id`
  (`lti_service.py:255`, `:231-240`).
- **Identity → auth user** — look up `lti_user_identity` by `(registration_id, sub)`; if absent,
  `_create_auth_user` (raw `INSERT INTO auth.users`, confirmed, `provider=lti`, token columns set
  to `''` to dodge GoTrue's NOT-NULL scan) and insert the identity `ON CONFLICT DO NOTHING`
  (`lti_service.py:258-276`, `:299-331`).
- **Membership** — if a school resolved, upsert
  `user_schools (user_id, school_id, school_role, is_primary=TRUE)`
  `ON CONFLICT (user_id, school_id) DO UPDATE SET school_role` (`lti_service.py:279-288`). **This is
  exactly the row the JWT claims hook + RLS middleware consume** (§4).

### Step 4 — session bridge + land on `/app?school_id=` — **[TO BUILD]** — see §5

Today `launch()` (`lti.py:106-119`) builds `{PUBLIC_BASE_URL}{LTI_REDIRECT_BASE}?school_id=…
&lti_uid=…` and sets a `gains_lti_launch=<user_id>` cookie that nothing consumes. **This does not
produce a Supabase session, so the middleware bounces to `/auth/login`.** §5 replaces this tail
with a signed handoff ticket + a Next.js bridge route that mints the session.

---

## 4. Per-School AuthN/AuthZ & Tenant Isolation

The LTI-resolved `school_id` flows through the existing, production-grade, browser-verified stack.
**Nothing new is required here — the launch just writes the membership row the stack already reads.**

### 4.1 The flow of `school_id` → RLS

1. **Membership.** `provision()` upserts `user_schools (user_id, school_id, school_role,
   is_primary=TRUE)` (`lti_service.py:279-288`). `school_role ∈ {admin, teacher, student, member}`
   (`user_schools.sql:22-23`); exactly one primary per user enforced by a partial unique index
   (`user_schools.sql:34-36`).
2. **JWT claims.** On the next token mint, `custom_access_token_hook` (SECURITY DEFINER, invoked by
   Supabase Auth) injects `school_ids TEXT[]`, `primary_school_id TEXT`, `is_super_admin BOOLEAN`
   from `user_schools` (`jwt_school_claims.sql:55-89`). It reads `user_schools` via a
   `GRANT SELECT ... TO supabase_auth_admin` (`user_schools.sql:53`). **The bridge (§5) must mint
   the session AFTER the membership exists so the very first token already carries the claim** —
   which it does, because `provision()` commits before the redirect.
3. **Backend extraction.** `get_current_user` reads the token from the `Authorization` header OR
   the Supabase SSR cookie (`dependencies.py:148-187`, `extract_token_from_cookies` `:115-145`);
   `extract_user_claims` pulls `school_ids`/`primary_school_id`/`is_super_admin` into `CurrentUser`.
4. **Per-request RLS.** `get_db_with_rls` (`rls.py:167-180`) → `set_school_id_for_session`
   (`rls.py:136-164`): **always** `SET LOCAL ROLE authenticated` first (drops the superuser RLS
   bypass — fail-closed, `rls.py:152-154`), then resolves the tenant (`?school_id` override →
   `primary_school_id` claim → super-admin Athenian fallback → None) and sets
   `SET LOCAL app.current_school_id = '<uuid>'` (`rls.py:161-163`). A member scoping to a school
   they don't belong to gets **HTTP 403** (`rls.py:107-120`, via `CurrentUser.can_access_school`).
5. **Row filter.** RLS `tenant_iso_select` on 35 per-tenant tables + `schools` enforces
   `school_id = current_setting('app.current_school_id', true)::uuid`
   (`rls_policies.sql:66-88`; fail-closed `NULLIF` hardening in
   `20260601000050_rls_failclosed_empty_guc.sql`). Unset GUC → matches zero rows.
6. **Frontend scoping.** `SelectedSchoolContext` adopts the `?school_id` from the launch redirect
   and threads it into every `/api/v1/...` report fetch.

### 4.2 Legacy equivalence

This is the direct moral equivalent of legacy's `__tenant` cookie + `_currentTenant.Change(...)` +
Power BI RLS `EffectiveIdentity` (R1 §4). Legacy resolved the tenant at LTI login from the
Schoology `tool_platform.name` via a per-tenant `SchoolName` setting; GAINS resolves it far more
robustly from the immutable `deployment_id` binding. The GAINS RLS/GUC layer replaces both ABP's
`IMultiTenant` filter and Power BI RLS in a single fail-closed mechanism, and it already covers
admin/teacher/student scoping.

### 4.3 IMS role → GAINS role mapping

`map_lti_roles` (`lti_service.py:53-70`) collapses the IMS `roles` array to a single
`school_role`, most-privileged wins, defaulting to `student` (least privilege):

| IMS LIS v2 role URI (matched by substring) | → GAINS `school_role` |
|---|---|
| `membership#Administrator`, `institution/person#Administrator`, `system/person#Administrator` | `admin` |
| `membership#Instructor`, `institution/person#Instructor`, `membership#ContentDeveloper`, `membership#TeachingAssistant` | `teacher` |
| `membership#Learner`, `institution/person#Student` | `student` |
| (no match) | `student` |

`school_role` is the **in-tenant** role (drives per-school report visibility). It is distinct from
the platform RBAC role (`super_admin`/`user`, cross-tenant) that governs `/admin`
(`user_schools.sql:8-16`). An LTI-provisioned user gets the platform `user` role from the new-user
trigger (`lti_service.py:300-301`) and their in-tenant role from the launch.

---

## 5. The Session-Bridge Gap (the Blocker) — Detailed Design

**Problem.** `launch()` 302s to `/app/...` with `gains_lti_launch=<user_id>`
(`lti.py:114-118`). That cookie is (a) **not a Supabase session** (`sb-<ref>-auth-token`), so
`middleware.ts:42` `getUser()` returns null and the browser is redirected to `/auth/login`
(`middleware.ts:49-54`); and (b) a **bare user id** — trivially forgeable, inviting impersonation /
session fixation (R6 §5.3). Both must be fixed.

**Constraint (CLAUDE.md).** Next.js = auth only; FastAPI = DB only. The **cookie-setting step MUST
live in a Next.js route**, because minting a Supabase session (setting `@supabase/ssr` cookies) is
an auth operation. FastAPI may create the `auth.users` row and the handoff ticket (DB writes) but
must NOT set session cookies.

### 5.1 Design: signed, single-use, short-TTL handoff ticket + a Next.js bridge route

**A. FastAPI mints a handoff ticket (replaces the bare-user-id cookie).** At the end of
`launch()`, instead of the `gains_lti_launch` cookie, insert a server-side ticket row and redirect
to the Next bridge carrying an opaque, unguessable ticket id.

- **New table** (migration, additive):
  ```
  lti_handoff_ticket(
    id            UUID PK DEFAULT uuid_generate_v7(),
    ticket        TEXT NOT NULL UNIQUE,      -- secrets.token_urlsafe(32); the opaque handle
    user_id       UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
    school_id     UUID REFERENCES schools(school_id) ON DELETE SET NULL,
    email         TEXT NOT NULL,             -- convenience for admin.generateLink
    consumed      BOOLEAN NOT NULL DEFAULT FALSE,
    expires_at    TIMESTAMPTZ NOT NULL,      -- now() + ~60s
    created_at    TIMESTAMPTZ NOT NULL DEFAULT now()
  )
  ```
  No RLS (service-role infrastructure, same rationale as the other `lti_*` tables,
  `20260601000020_lti.sql:64-65`).
- **Token shape.** The `ticket` is a 256-bit `secrets.token_urlsafe(32)` random handle — an opaque
  DB key, NOT a JWT. All authority (user_id, school_id) lives in the server-side row, so the
  browser only ever holds an unguessable pointer. (If a stateless variant is ever wanted, an
  HMAC-signed JWT bound to `user_id`+`school_id`+`jti` with server-side `jti` single-use tracking
  is the alternative — but the DB-row approach reuses the exact `lti_launch_session` pattern
  already in the codebase and is simpler to make truly single-use.)
- **TTL.** ~60 seconds (tighter than the 300s launch TTL — the browser redirect from FastAPI to
  Next is immediate).
- **Storage.** Server-side row (above), written by FastAPI as service_role. The browser carries
  only `?ticket=<handle>` in the 302 `Location`. Do **not** put it in a cookie (a cookie survives;
  a one-shot URL param + server-side consume does not).
- **Redirect.** `302 → {PUBLIC_BASE_URL}/api/lti/bridge?ticket=<handle>` (a Next route, not
  `/app`). Delete the `gains_lti_launch` cookie logic (`lti.py:114-118`).

**B. Next.js bridge route exchanges the ticket for a Supabase session.** New route
`frontend/src/app/api/lti/bridge/route.ts` (`GET`, because the platform's browser navigation lands
here via 302):

1. Read `?ticket`. Reject if absent → redirect `/auth/login?error=invalid_launch`.
2. **Validate + consume the ticket single-use.** Call FastAPI (service-authenticated, e.g. a
   machine-auth endpoint `POST /api/v1/lti/consume-ticket` guarded by a shared secret like the
   ingestion pattern `config.py:53-56`) OR read+consume via the service-role Supabase client
   directly in Next. It must atomically check `consumed=FALSE AND expires_at > now()`, mark
   `consumed=TRUE`, and return `{ user_id, email, school_id }`. Any failure →
   `/auth/login?error=invalid_launch`. **Single-use is mandatory** (mirror `_consume_state`
   `lti_service.py:176-197`).
3. **Mint the session** using the service-role admin API + the existing verify pattern:
   `admin.generateLink({ type: 'magiclink', email })` → returns a `token_hash` (and/or an action
   link). This is the same GoTrue mechanism the magic-link flow already relies on
   (`frontend/src/app/api/auth/magic-link/route.ts:48-53` uses `signInWithOtp`; the confirm route
   already calls `verifyOtp` — see step 4).
4. **Set the SSR cookies** by calling `supabase.auth.verifyOtp({ type: 'magiclink', token_hash })`
   on a server SSR client — **exactly** the mechanism `frontend/src/app/api/auth/confirm/route.ts:47`
   already uses to establish a session and set `@supabase/ssr` cookies. (Alternatively, follow the
   `exchangeCodeForSession` path from `callback/route.ts:41`; `verifyOtp` is the closer fit because
   `generateLink` yields a `token_hash`.) At this point the browser holds a real
   `sb-<ref>-auth-token` cookie, and because `provision()` already wrote the `user_schools` row, the
   freshly minted token carries `school_ids` including the launched school.
5. **MFA gate.** LTI users are provisioned with no MFA factors
   (`provider=lti`, `lti_service.py:323`), so `getAuthenticatorAssuranceLevel()` returns
   `currentLevel === nextLevel === 'aal1'` and the confirm-route MFA check passes cleanly. Reuse
   the confirm route's fail-closed MFA handling verbatim (`confirm/route.ts:67-80`): on AAL error,
   `signOut()` then redirect to login. (Policy decision for the owner in §11: should LTI users ever
   be forced through MFA? Default: no — they authenticated at Schoology.)
6. **Redirect** `302 → /app/reports/standard-summary?school_id=<school_id>` (the value of
   `LTI_REDIRECT_BASE` `lti.py:29`). `SelectedSchoolContext` adopts `?school_id`. The Next
   middleware now sees a valid session and lets the request through (`middleware.ts:42-54`).

**C. Why this is safe.**

- The browser never holds authority — only an opaque, single-use, 60s ticket handle. Consuming it
  is atomic and one-shot (impersonation/fixation closed).
- The session is minted by GoTrue (`generateLink`/`verifyOtp`), not hand-forged, so it is a
  first-class Supabase session with a properly signed JWT carrying the claims hook's output.
- Cookie-setting stays in Next (CLAUDE.md compliant); FastAPI only does DB writes + a redirect.

### 5.2 Session-mint mechanism — recommendation

**Recommended: `admin.generateLink({ type: 'magiclink' })` → `verifyOtp`** (option A). Rationale:
it reuses two existing, security-reviewed patterns (`confirm/route.ts` verifyOtp;
`callback/route.ts` MFA-fail-closed), it goes through GoTrue so the session is legitimate, and it
requires no new session-forging code. The `admin.generateLink` call needs the **service-role key**,
which already exists server-side (`SUPABASE_SERVICE_KEY`, `config.py:29`; used by
`school_service.py`). Do NOT hand-mint a JWT with the service key and set it as a cookie directly —
that bypasses GoTrue's session bookkeeping and is harder to reason about.

---

## 6. Onboarding / Integration Points per School

### 6.1 Per-school onboarding procedure

For each new school (R4 §3.2–3.4, §4):

1. **District admin installs the GAINS app** in that school's Schoology organization. The app is
   **district-internal** (only that district uses it), so it **bypasses App Center public review**
   (R4 §3.6) — install directly. Installation **mints the `deployment_id`** (found under
   *Organization Apps → Configure*).
2. **Admin sends us `client_id` + `deployment_id`.** Schoology renders the deployment id as the
   whole string `"{client_id}-{n}"` (e.g. `9345826612-1749208473`); the `deployment_id` claim in
   the id_token is that **full** value. Store it exactly as *Configure* shows it
   (`20260601000020_lti.sql:34` documents this; match on it in `_resolve_school`
   `lti_service.py:231-240`). R4 §3.3.
3. **We insert the binding.** If this is a **new `client_id`**, insert an `lti_registration` row
   with Schoology's four **fixed** platform URLs (already in the seed template,
   `seed_lti.py:44-49`: issuer `https://schoology.schoology.com`, authorize
   `.../authorize-redirect`, token `.../access-token`, JWKS `.../.well-known/jwks`) and a freshly
   generated 2048-bit tool keypair + `tool_kid` (`seed_lti.py:67`). Then insert an `lti_deployment`
   row binding `deployment_id → school_id`. If the `client_id` already exists (same app across
   schools), only the `lti_deployment` row is new.
4. **Give the district admin our three tool URLs** for the Schoology app config (R4 §3.2):
   - Redirect / Target Link URI = `{PUBLIC_BASE_URL}/api/v1/lti/launch`
   - OIDC login-init URL = `{PUBLIC_BASE_URL}/api/v1/lti/login`
   - Public JWKS URL = `{PUBLIC_BASE_URL}/api/v1/lti/.well-known/jwks.json` (`lti.py:122-126`).
5. **Verify** with the mock harness against a staging copy, then a real launch smoke test.

### 6.2 Onboarding UX — recommendation

Two options:

- **(Recommended for the pilot) A documented SQL/CLI onboarding procedure** — extend
  `supabase/seeds/seed_lti.py` with a small `bind` subcommand (`--issuer --client-id
  --deployment-id --school-short-name`) that inserts the `lti_registration` (if new) + the
  `lti_deployment` binding. This is the least code, matches the current `seed` pattern
  (`seed_lti.py:65-87`), and fits the small known-school set. The placeholder
  `client_id = 'REPLACE_AFTER_SCHOOLOGY_INSTALL'` (`seed_lti.py:74,78`) is replaced per school.
- **(Later) An admin "LTI Registrations / Deployments" module** — a first-class admin UI to add a
  registration, bind a deployment to a school, and view the tool JWKS. No such UI exists today.
  Worth building only once onboarding cadence justifies it; the CLI covers the pilot.

### 6.3 Known target schools

From the legacy auth-server CSP allow-list (R1 §3.2), the Schoology-integrated schools are:
`aaota` (**Athenian**), `brightviewprep`, `southpsa`, **`crestwell`**, **`cfprep` (CFP)**. The three
schools currently loaded in prod are **Athenian / CFP / Crestwell**. Each needs its own
`(client_id?, deployment_id) → school_id` binding.

---

## 7. Iframe / CSP Posture

Schoology typically launches an LTI tool **inside an iframe** on the course page.

- **Cookies must be cross-site.** The Supabase SSR session cookies AND the bridge flow must work in
  a third-party (iframe) context, i.e. `SameSite=None; Secure`. The current launch cookie already
  uses `samesite="none", secure=True` (`lti.py:117`) — the *bridge* cookies (the `sb-...-auth-token`
  set by `verifyOtp`) must be configured the same way via the `@supabase/ssr` cookie options.
- **`frame-ancestors`.** Set a Content-Security-Policy `frame-ancestors` (and drop
  `X-Frame-Options: DENY` for the launch surface) allowing `https://*.schoology.com` and
  `https://app.schoology.com` so the GAINS pages may be framed by Schoology — mirroring legacy's
  auth-server CSP (R1 §3.2). This must be scoped to the launch/app surface only, not the whole site.
- **Third-party-cookie caveat.** Modern browsers increasingly **block third-party cookies** by
  default. Supabase's chunked SSR cookies (`sb-<ref>-auth-token.0/.1`, handled at
  `dependencies.py:120-121`) under `SameSite=None` inside a `*.schoology.com` iframe **may be
  blocked** — this **must be tested on real target browsers/Schoology**, not assumed (R6 §3D,
  RESEARCH_BRIEF §5.6). If blocked, fall back to **new-tab launch**.
- **New-tab vs embedded decision.** Recommended **default: launch in a new tab / full window**
  (`window.name`/target `_blank` or a launch-presentation `window` hint), which sidesteps the
  third-party-cookie problem entirely and gives the dashboard full width. Offer embedded iframe as
  an option only after verifying cookie behavior on the district's actual browsers. This is a
  correctness-affecting choice — see §11.

---

## 8. LTI Advantage (Optional, Later)

The tool already **publishes its JWKS** (`lti.py:122-126`, `tool_jwks` `lti_service.py:334-346`) and
**stores a per-registration private key** (`lti_registration.tool_private_key`
`20260601000020_lti.sql:22`), so outbound Advantage service calls are **scaffolded but not
implemented** — there is no code that mints an outbound OAuth2 client-credentials JWT-bearer token
against the platform `auth_token_url`.

- **NRPS (Names & Role Provisioning) — roster.** Optional. Lets the backend pull a course-section
  roster server-side without every user launching. Scope
  `.../lti-nrps/scope/contextmembership.readonly`; Schoology caps 100 records/request and pages via
  `Link` headers (R4 §2.2). Build only if server-side roster prefetch is wanted.
- **AGS (Assignment & Grade Services) — grades.** Optional, read-only side only
  (`result.readonly`, `lineitem.readonly`). **Critical:** AGS exposes only **assignment-level
  gradebook scores, NOT per-question response detail** (R4 §2.3). GAINS' `fact_student_submission`
  grain and question-summary cubes need per-question data, so **AGS does NOT and cannot replace the
  scraper as the ingestion data source.** AGS is at best "live grade" garnish.
- **Deep Linking — skip.** It is a content-selection/placement workflow (a teacher pins a resource),
  not analytics (R4 §2.4). A single resource-link launch suffices for a dashboard.

**Recommendation:** defer all Advantage services. Ship the plain launch-to-dashboard first. Add
NRPS later only if a roster prefetch need emerges.

---

## 9. Security Considerations

- **Replay / nonce / single-use state — [BUILT, verify].** `_consume_state` gives true one-shot use
  (`lti_service.py:176-197`); nonce equality enforced (`:211-212`); state has a 300s TTL. Verify
  under load that concurrent double-POST of the same `state` cannot both win (the
  `UPDATE ... SET consumed=TRUE` + commit should serialize; consider `SELECT ... FOR UPDATE` if a
  race is observed).
- **Handoff-token forgery / session fixation — [TO BUILD, §5].** The current
  `gains_lti_launch=<user_id>` cookie is forgeable and MUST be replaced by the signed/opaque,
  single-use, 60s, server-stored ticket. Non-negotiable (R6 §5.3, RESEARCH_BRIEF §5.5).
- **id_token signature + audience — [BUILT].** RS256 via platform JWKS by `kid`; `aud` must equal
  our `client_id`; `iss` must equal the registration issuer (`lti_service.py:202-209`). A launch
  cannot forge a foreign tenant.
- **Issuer-only registration fallback — [verify/fix].** §2.2 caveat: require `client_id` at login
  (or drop the issuer-only fallback) when >1 Schoology registration exists, so tenants are never
  matched non-deterministically.
- **Third-party cookies — [TO BUILD/test, §7].** Test real-browser behavior; default to new-tab if
  blocked.
- **CSRF on the bridge.** The bridge `GET` lands via the platform's browser 302, so it can't carry a
  same-origin token; its safety comes from the **single-use ticket**, not `enforceSameOrigin`. Any
  bridge **mutation** endpoint (e.g. a `POST /consume-ticket`) must use machine-auth (shared secret)
  or be internal-only, not the user-session CSRF check.
- **`LTI_ENABLED` gating — [BUILT].** Routes are only registered when the flag is on
  (`router.py:54-55`); off by default (`config.py:46`) so no LTI code can provision `auth.users` /
  `user_schools` while dormant. Keep it off until Phases A–D land.
- **No secrets in code.** Tool private keys live in `lti_registration` (DB), Schoology `client_id`
  is per-registration data, and `SUPABASE_SERVICE_KEY` / any `INGESTION_TRIGGER_SECRET`-style bridge
  secret live in env — never committed (project memory: no-secrets-in-repo). Treat all legacy
  Schoology/Azure secrets as compromised; generate a fresh tool keypair (`seed_lti.py:67`).
- **RLS fail-closed — [BUILT].** Even a mis-provisioned LTI user with no membership resolves to no
  tenant → RLS returns zero rows (`rls.py:152-157`, `rls_policies.sql:69`). The launch cannot leak
  another school's data.

---

## 10. Phased Implementation Roadmap (for a LATER phase — do NOT implement now)

Ordered. Effort estimates are rough (1 engineer).

### Phase A — Session bridge + handoff ticket (THE blocker) — ~3–5 days
- Migration: `lti_handoff_ticket` table (additive, no RLS) (§5.1A).
- Backend: replace the `gains_lti_launch` cookie tail of `launch()` (`lti.py:106-119`) with a
  ticket insert + 302 to `/api/lti/bridge?ticket=…`; add a machine-auth `consume-ticket`
  path (atomic single-use).
- Frontend: `frontend/src/app/api/lti/bridge/route.ts` — validate+consume ticket →
  `admin.generateLink({type:'magiclink'})` → `verifyOtp` (set SSR cookies) → MFA fail-closed →
  302 `/app/...?school_id=` (§5.1B). Reuse `confirm/route.ts` + `callback/route.ts` patterns.
- Verify end-to-end with the mock harness (`seed_lti.py launch`) pointed through the bridge.

### Phase B — Onboarding (registration/deployment seeding) — ~1–2 days
- Extend `seed_lti.py` with a `bind` subcommand (insert `lti_registration` if new + `lti_deployment`
  binding) (§6.2). Document the per-school procedure (§6.1). Deliver the three tool URLs.
- (Optional/later) admin "LTI Registrations/Deployments" module.

### Phase C — Iframe / CSP + enablement — ~2–3 days
- Set `frame-ancestors *.schoology.com` on the launch/app surface; ensure bridge + Supabase cookies
  are `SameSite=None; Secure` (§7). Decide + implement new-tab vs embedded.
- **Test third-party-cookie behavior on real Schoology + target browsers.**
- Flip `LTI_ENABLED=True` in staging, then prod (`config.py:46`).

### Phase D — Tests — ~3–4 days (none exist today)
- Launch validation (happy path, bad signature, wrong `aud`/`iss`, expired, wrong `message_type`).
- Replay rejection (reused `state`, reused `nonce`, expired state).
- Role/tenant mapping (each IMS role → correct `school_role`; `deployment_id` → correct
  `school_id`; unknown deployment → no school).
- Session bridge (ticket single-use, expiry, forged/absent ticket rejected, cookie set, correct
  `school_id` in redirect, RLS scopes to that school and 403s a foreign school).
- The "tests" referenced in the roadmap are the mock harness only (R6 §3F) — real pytest coverage
  is greenfield.

### Phase E — (Optional) LTI Advantage NRPS — ~4–6 days
- Implement outbound client-credentials JWT-bearer token minting against `auth_token_url`; NRPS
  roster fetch with paging. Only if server-side roster prefetch is wanted (§8). AGS/Deep Linking
  skipped.

**Critical path to a working launch: A → B → C → D.** E is optional and independent.

---

## 11. Open Questions for the Owner (correctness / blocking)

1. **Real Schoology registration data.** Phase 3 cannot function without each district's real
   `client_id` + `deployment_id`, which require a **district-admin app install** in each school's
   Schoology org (R4 §4, R6 §3C). Owner must confirm access / drive the installs for Athenian
   (aaota), CFP (cfprep), Crestwell (and any others).
2. **Multi-building under one deployment.** Does any target district install ONE Schoology
   deployment spanning multiple buildings/schools? If yes, `deployment_id` alone maps to a district,
   not a GAINS school, and a **custom-param (building id) disambiguator** is required in the id_token
   `custom` claim before launch can resolve the right tenant (R4 §3.5, §4). Today `_resolve_school`
   assumes one deployment → one school (`lti_service.py:231-240`).
3. **App Center review vs district-internal install.** Confirm all target schools go the
   **district-internal** path (no ~1-month App Center review). If GAINS is ever listed publicly,
   the review process applies (R4 §3.6).
4. **Iframe vs new tab.** Decide the supported launch mode given third-party-cookie risk (§7).
   Recommended default: new tab.
5. **MFA policy for LTI users.** Do LTI users (already authenticated at Schoology) bypass GAINS
   MFA (default: yes), or inherit the MFA gate (`middleware.ts:74-84`)? (§5.1 step 5.)
6. **Primary-school re-scoping.** An LTI user is upserted `is_primary=TRUE` for the launched school,
   but a second launch from a different school updates only `school_role`, not `is_primary`
   (`lti_service.py:283-285`). For multi-school users, is per-launch `?school_id` (already carried)
   sufficient, or should each launch re-scope the primary? (Default: rely on `?school_id`.)

---

## 12. Scope Note

**This is a plan. Nothing here is implemented.** No `lti.py` / `lti_service.py` / migration /
frontend file was modified in producing it; no commit was made. LTI remains gated OFF
(`LTI_ENABLED=False`, `backend/app/core/config.py:46`), so no `/api/v1/lti/*` route is registered
and no LTI code path can provision `auth.users` / `user_schools` today. The LTI 1.3 protocol
surface and the per-school RLS/tenancy stack described above are already built and verified in the
codebase; the remaining work (session bridge, onboarding seeding, iframe/CSP, tests, enablement) is
specified here for a **later implementation phase that begins only after owner review and greenlight.**
```