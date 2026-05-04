import { NextRequest, NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';
import { enforceSameOrigin } from '@/lib/utils/origin';

export async function POST(request: NextRequest) {
  try {
    const originError = enforceSameOrigin(request);
    if (originError) return originError;

    const supabase = await createSSRClient();
    const { data: { user } } = await supabase.auth.getUser();

    if (!user) {
      return NextResponse.json({ error: 'Unauthorized' }, { status: 401 });
    }

    const body = await request.json();
    const { factorId, challengeId, code } = body;

    if (!factorId || !challengeId || !code) {
      return NextResponse.json(
        { error: 'Factor ID, challenge ID, and code are required' },
        { status: 400 }
      );
    }

    const { error } = await supabase.auth.mfa.verify({
      factorId,
      challengeId,
      code
    });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    return NextResponse.json({ success: true });
  } catch (error) {
    console.error('Error verifying MFA code:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
