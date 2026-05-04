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
    const { friendlyName } = body;

    if (!friendlyName || typeof friendlyName !== 'string') {
      return NextResponse.json(
        { error: 'Friendly name is required' },
        { status: 400 }
      );
    }

    const { data, error } = await supabase.auth.mfa.enroll({
      factorType: 'totp',
      friendlyName: friendlyName.trim()
    });

    if (error) {
      return NextResponse.json({ error: error.message }, { status: 400 });
    }

    return NextResponse.json({
      factorId: data.id,
      qrCode: data.totp.qr_code
    });
  } catch (error) {
    console.error('Error enrolling MFA factor:', error);
    return NextResponse.json(
      { error: 'Internal server error' },
      { status: 500 }
    );
  }
}
