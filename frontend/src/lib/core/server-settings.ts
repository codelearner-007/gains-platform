import { z } from 'zod';
import { publicEnvSchema } from './public-settings';

const rateLimitPattern = /^[0-9]+\/(second|seconds|minute|minutes|hour|hours|day|days|week|weeks|month|months|year|years)$/;

const serverOnlySchema = z.object({
  PRIVATE_SUPABASE_SERVICE_KEY: z.string(),
  // Google sign-in credential. Empty/unset means Google is not configured and
  // the Google button is hidden; this is the source of truth for that gate.
  SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID: z.string().default(''),
  FRONTEND_REDIS_URL: z.string().default(''),
  FRONTEND_REDIS_PREFIX: z.string().default('starter_template'),
  FRONTEND_RATE_LIMIT_AUTH_ME: z.string().regex(rateLimitPattern).default('60/minute'),
  FRONTEND_RATE_LIMIT_AUTH_LOGIN: z.string().regex(rateLimitPattern).default('10/minute'),
  FRONTEND_RATE_LIMIT_AUTH_REGISTER: z.string().regex(rateLimitPattern).default('5/minute'),
  FRONTEND_RATE_LIMIT_AUTH_FORGOT_PASSWORD: z.string().regex(rateLimitPattern).default('5/minute'),
  FRONTEND_RATE_LIMIT_AUTH_CHANGE_PASSWORD: z.string().regex(rateLimitPattern).default('5/minute'),
  FRONTEND_RATE_LIMIT_AUTH_RESET_PASSWORD: z.string().regex(rateLimitPattern).default('2/minute'),
  FRONTEND_RATE_LIMIT_ENABLED: z.coerce.boolean().default(true),
  /**
   * Behavior when Redis is configured but unreachable / errors out.
   * - true → bypass the limiter (fail-open) — convenient in dev, risky in prod.
   * - false (default) → return 503 (fail-closed) — secure default.
   *
   * When FRONTEND_REDIS_URL is empty (Redis intentionally not configured),
   * the limiter always bypasses regardless of this flag.
   */
  FRONTEND_RATE_LIMIT_FAIL_OPEN: z.coerce.boolean().default(false),
});

const serverEnvSchema = publicEnvSchema.merge(serverOnlySchema);

const env = serverEnvSchema.parse({
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  NEXT_PUBLIC_PRODUCTNAME: process.env.NEXT_PUBLIC_PRODUCTNAME,
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
  NODE_ENV: process.env.NODE_ENV,
  PRIVATE_SUPABASE_SERVICE_KEY: process.env.PRIVATE_SUPABASE_SERVICE_KEY,
  SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID:
    process.env.SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID,
  FRONTEND_REDIS_URL: process.env.FRONTEND_REDIS_URL,
  FRONTEND_REDIS_PREFIX: process.env.FRONTEND_REDIS_PREFIX,
  FRONTEND_RATE_LIMIT_AUTH_ME: process.env.FRONTEND_RATE_LIMIT_AUTH_ME,
  FRONTEND_RATE_LIMIT_AUTH_LOGIN: process.env.FRONTEND_RATE_LIMIT_AUTH_LOGIN,
  FRONTEND_RATE_LIMIT_AUTH_REGISTER: process.env.FRONTEND_RATE_LIMIT_AUTH_REGISTER,
  FRONTEND_RATE_LIMIT_AUTH_FORGOT_PASSWORD:
    process.env.FRONTEND_RATE_LIMIT_AUTH_FORGOT_PASSWORD,
  FRONTEND_RATE_LIMIT_AUTH_CHANGE_PASSWORD:
    process.env.FRONTEND_RATE_LIMIT_AUTH_CHANGE_PASSWORD,
  FRONTEND_RATE_LIMIT_AUTH_RESET_PASSWORD:
    process.env.FRONTEND_RATE_LIMIT_AUTH_RESET_PASSWORD,
  FRONTEND_RATE_LIMIT_ENABLED: process.env.FRONTEND_RATE_LIMIT_ENABLED,
  FRONTEND_RATE_LIMIT_FAIL_OPEN: process.env.FRONTEND_RATE_LIMIT_FAIL_OPEN,
});

export const serverSettings = Object.freeze({
  ...env,
});

export type ServerSettings = typeof serverSettings;
