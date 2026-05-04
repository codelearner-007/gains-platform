import { createServerClient } from '@supabase/ssr'
import {Database} from "@/lib/types/database.types";
import { serverSettings } from '../core/server-settings';

export async function createServerAdminClient() {

    return createServerClient<Database>(
        serverSettings.NEXT_PUBLIC_SUPABASE_URL,
        serverSettings.PRIVATE_SUPABASE_SERVICE_KEY,
        {
            cookies: {
                getAll: () => [],
                setAll: () => {},
            },
            auth: {
                persistSession: false,
                autoRefreshToken: false,
            },
            db: {
                schema: 'public'
            },
        }
    )
}

/**
 * Revoke all sessions for a specific user via GoTrue admin API.
 * This forces the user to re-authenticate on all devices.
 */
export async function revokeAllUserSessions(userId: string): Promise<void> {
    const url = `${serverSettings.NEXT_PUBLIC_SUPABASE_URL}/auth/v1/admin/users/${userId}/logout`;
    const res = await fetch(url, {
        method: 'POST',
        headers: {
            'Authorization': `Bearer ${serverSettings.PRIVATE_SUPABASE_SERVICE_KEY}`,
            'apikey': serverSettings.PRIVATE_SUPABASE_SERVICE_KEY,
        },
    });
    if (!res.ok) {
        console.error(`Failed to revoke sessions for user ${userId}: ${res.status}`);
    }
}