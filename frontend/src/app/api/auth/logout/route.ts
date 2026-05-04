import { NextRequest, NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { enforceSameOrigin } from '@/lib/utils/origin';

export async function POST(request: NextRequest) {
  try {
    const originError = enforceSameOrigin(request);
    if (originError) return originError;

    const supabase = await createSSRClient();
    const { error: signOutError } = await supabase.auth.signOut();

    if (signOutError) {
      return NextResponse.json({ error: signOutError.message }, { status: 400 });
    }

    return NextResponse.json({ message: 'Logged out successfully' });
  } catch {
    return NextResponse.json({ error: 'Internal server error' }, { status: 500 });
  }
}
