import {createServerClient} from '@supabase/ssr'
import {cookies} from 'next/headers'
import {Database} from "@/lib/types/database.types";
import { publicSettings } from '../core/public-settings';

export async function createSSRClient() {
    const cookieStore = await cookies()

    return createServerClient<Database, "public">(
        publicSettings.NEXT_PUBLIC_SUPABASE_URL,
        publicSettings.NEXT_PUBLIC_SUPABASE_ANON_KEY,
        {
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