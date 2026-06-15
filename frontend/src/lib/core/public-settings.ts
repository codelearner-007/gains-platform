import { z } from 'zod';

/** Zod schema for vars safe to load in the browser / edge middleware (no secrets). */
export const publicEnvSchema = z.object({
  NEXT_PUBLIC_SUPABASE_URL: z.string().default('http://127.0.0.1:55321'),
  NEXT_PUBLIC_SUPABASE_ANON_KEY: z.string(),
  NEXT_PUBLIC_PRODUCTNAME: z.string().default('GAINS'),
  NEXT_PUBLIC_API_URL: z.string().url().default('http://localhost:8000'),
  NEXT_PUBLIC_SITE_URL: z.string().url().default('http://localhost:3000'),
  NODE_ENV: z.enum(['development', 'production', 'test']).default('development'),
  /** Empty when unset — GA is optional; required env would break all routes importing public-settings. */
  NEXT_PUBLIC_GA_MEASUREMENT_ID: z.string().default(''),
});

// In browser bundles, parsing `process.env` directly is unreliable because Next.js
// only guarantees inlining for direct property access (`process.env.NEXT_PUBLIC_*`).
const env = publicEnvSchema.parse({
  NEXT_PUBLIC_SUPABASE_URL: process.env.NEXT_PUBLIC_SUPABASE_URL,
  NEXT_PUBLIC_SUPABASE_ANON_KEY: process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY,
  NEXT_PUBLIC_PRODUCTNAME: process.env.NEXT_PUBLIC_PRODUCTNAME,
  NEXT_PUBLIC_API_URL: process.env.NEXT_PUBLIC_API_URL,
  NEXT_PUBLIC_SITE_URL: process.env.NEXT_PUBLIC_SITE_URL,
  NODE_ENV: process.env.NODE_ENV,
  NEXT_PUBLIC_GA_MEASUREMENT_ID:process.env.NEXT_PUBLIC_GA_MEASUREMENT_ID,
});

export const publicSettings = Object.freeze({
  ...env,
});

export type PublicSettings = typeof publicSettings;
