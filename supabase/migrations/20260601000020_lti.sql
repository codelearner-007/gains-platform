-- ============================================================================
-- LTI 1.3 / Advantage tool-provider tables
-- ============================================================================
-- Lets the platform be launched from Schoology/Canvas exactly like the legacy
-- EdvanceLearning GAINS tool (which was LTI 1.3, OIDC + id_token). Mirrors the
-- legacy PlatformTool / deployment model.
--
--   lti_registration  — trust config for one platform client (per school/org)
--   lti_deployment    — (registration, deployment_id) -> tenant school binding
--   lti_launch_session— single-use state/nonce for OIDC replay protection
--   lti_user_identity — (registration, sub) -> auth.users mapping (external id)
-- ============================================================================

CREATE TABLE IF NOT EXISTS public.lti_registration (
  id               UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  issuer           TEXT NOT NULL,                  -- e.g. https://schoology.schoology.com
  client_id        TEXT NOT NULL,                  -- tool client_id at this platform
  platform_name    TEXT,                           -- friendly label (Schoology/Canvas)
  auth_login_url   TEXT NOT NULL,                  -- platform OIDC authorize-redirect
  auth_token_url   TEXT NOT NULL,                  -- platform OAuth2 token endpoint
  jwks_url         TEXT NOT NULL,                  -- platform JWKS (verifies id_token)
  tool_private_key TEXT NOT NULL,                  -- PEM; signs our outbound JWTs (AGS/NRPS/DL)
  tool_kid         TEXT NOT NULL,                  -- kid we publish in /.well-known/jwks.json
  is_active        BOOLEAN NOT NULL DEFAULT TRUE,
  created_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (issuer, client_id)
);
CREATE INDEX lti_registration_issuer_idx ON public.lti_registration (issuer);

CREATE TABLE IF NOT EXISTS public.lti_deployment (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  registration_id UUID NOT NULL REFERENCES public.lti_registration(id) ON DELETE CASCADE,
  deployment_id   TEXT NOT NULL,                   -- Schoology stores "{client_id}-{n}" whole
  school_id       UUID REFERENCES public.schools(school_id) ON DELETE SET NULL,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (registration_id, deployment_id)
);
CREATE INDEX lti_deployment_school_idx ON public.lti_deployment (school_id);

CREATE TABLE IF NOT EXISTS public.lti_launch_session (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  state           TEXT NOT NULL,
  nonce           TEXT NOT NULL,
  registration_id UUID NOT NULL REFERENCES public.lti_registration(id) ON DELETE CASCADE,
  target_link_uri TEXT,
  consumed        BOOLEAN NOT NULL DEFAULT FALSE,
  expires_at      TIMESTAMPTZ NOT NULL,            -- ~5 min TTL
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX lti_launch_session_state_idx ON public.lti_launch_session (state);
CREATE INDEX lti_launch_session_expires_idx ON public.lti_launch_session (expires_at);

CREATE TABLE IF NOT EXISTS public.lti_user_identity (
  id              UUID PRIMARY KEY DEFAULT uuid_generate_v7(),
  registration_id UUID NOT NULL REFERENCES public.lti_registration(id) ON DELETE CASCADE,
  sub             TEXT NOT NULL,                   -- platform-stable user id
  user_id         UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (registration_id, sub)
);
CREATE INDEX lti_user_identity_user_idx ON public.lti_user_identity (user_id);

-- These tables are managed only by FastAPI as service_role (LTI launch flow and
-- admin registration). No tenant RLS — they are infrastructure, not tenant data.
