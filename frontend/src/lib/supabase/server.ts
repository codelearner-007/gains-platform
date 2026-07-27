import {createServerClient, type CookieOptionsWithName} from '@supabase/ssr'
import {cookies} from 'next/headers'
import {Database} from "@/lib/types/database.types";
import { publicSettings } from '../core/public-settings';

/**
 * @param cookieOptions Optional per-call override for the attributes applied to
 *   the Supabase session cookies this client sets. Merged over
 *   `@supabase/ssr`'s DEFAULT_COOKIE_OPTIONS (sameSite:'lax', path:'/', …), so
 *   only the keys passed change. LEAVE UNSET for normal web auth (password
 *   login, OAuth, email confirm) — the Lax default is the correct same-origin
 *   CSRF posture. The ONLY caller that overrides is the LTI bridge, which needs
 *   `SameSite=None; Secure` so the session survives inside a *.schoology.com
 *   iframe (and only in production/HTTPS — SameSite=None requires Secure).
 * @param opts.partitioned When true, stamps `Partitioned` (CHIPS) on the session
 *   cookies. Required for the iframe launch: modern Chrome blocks unpartitioned
 *   third-party cookies, so without CHIPS the SameSite=None session cookie is
 *   dropped inside the Schoology iframe. @supabase/ssr (0.8.0) does NOT forward
 *   `partitioned` from cookieOptions, so it is applied here at the `cookieStore.set`
 *   boundary (Next 16 serializes it). Bridge-only — same-site auth must NOT be
 *   partitioned.
 */
export async function createSSRClient(
    cookieOptions?: CookieOptionsWithName,
    opts?: { partitioned?: boolean },
) {
    const cookieStore = await cookies()

    return createServerClient<Database, "public">(
        publicSettings.NEXT_PUBLIC_SUPABASE_URL,
        publicSettings.NEXT_PUBLIC_SUPABASE_ANON_KEY,
        {
            ...(cookieOptions ? { cookieOptions } : {}),
            cookies: {
                getAll() {
                    return cookieStore.getAll()
                },
                setAll(cookiesToSet) {
                    try {
                        cookiesToSet.forEach(({ name, value, options }) =>
                            cookieStore.set(
                                name,
                                value,
                                opts?.partitioned
                                    ? { ...options, partitioned: true }
                                    : options,
                            )
                        )
                    } catch {
                        // The `setAll` method was called from a Server Component.
                        // This can be ignored if you have middleware refreshing
                        // user sessions.
                    }
                },
            }
        }
    )
}