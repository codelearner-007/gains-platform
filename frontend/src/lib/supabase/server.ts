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
 */
export async function createSSRClient(cookieOptions?: CookieOptionsWithName) {
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
                            cookieStore.set(name, value, options)
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