import {createBrowserClient} from '@supabase/ssr'
import {Database} from "@/lib/types/database.types";
import { publicSettings } from '../core/public-settings';

export function createSPAClient() {
    return createBrowserClient<Database, "public">(
        publicSettings.NEXT_PUBLIC_SUPABASE_URL,
        publicSettings.NEXT_PUBLIC_SUPABASE_ANON_KEY
    )
}