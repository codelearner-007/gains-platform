import { NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';

export async function GET() {
  try {
    const supabase = await createSSRClient();
    const { data: { user }, error: sessionError } = await supabase.auth.getUser();

    if (sessionError || !user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const { data: aal, error: aalError } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();

    if (aalError) {
      return NextResponse.json({ error: aalError.message }, { status: 400 });
    }

    return NextResponse.json({
      currentLevel: aal.currentLevel,
      nextLevel: aal.nextLevel
    });
  } catch (error) {
    console.error('Error checking MFA status:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
