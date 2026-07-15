import { NextResponse } from 'next/server';
import { createSSRClient } from '@/lib/supabase/server';

const ALLOWED_TYPES = [
  'invite',
  'magiclink',
  'recovery',
  'email_change',
  'email',
] as const;

type ConfirmType = (typeof ALLOWED_TYPES)[number];

const ALLOWED_NEXT_PREFIXES = [
  '/app',
  '/admin',
  '/auth/reset-password',
  '/auth/accept-invite',
  '/auth/2fa',
];

function isAllowedNext(next: string | null): boolean {
  if (!next) return false;
  if (!next.startsWith('/') || next.startsWith('//') || next.startsWith('/\\')) return false;
  return ALLOWED_NEXT_PREFIXES.some(
    (prefix) => next === prefix || next.startsWith(`${prefix}/`) || next.startsWith(`${prefix}?`),
  );
}

function isConfirmType(value: string | null): value is ConfirmType {
  return !!value && (ALLOWED_TYPES as readonly string[]).includes(value);
}

export async function GET(request: Request) {
  const url = new URL(request.url);
  const tokenHash = url.searchParams.get('token_hash');
  const type = url.searchParams.get('type');
  const nextParam = url.searchParams.get('next');
  const next = isAllowedNext(nextParam) ? nextParam! : '/app';

  if (!tokenHash || !isConfirmType(type)) {
    return NextResponse.redirect(new URL('/auth/login?error=invalid_link', request.url));
  }

  const supabase = await createSSRClient();
  const { error } = await supabase.auth.verifyOtp({ type, token_hash: tokenHash });

  if (error) {
    console.error('Email confirmation failed:', error.message);
    return NextResponse.redirect(
      new URL(
        `/auth/login?error=${encodeURIComponent('Confirmation link is invalid or expired')}`,
        request.url,
      ),
    );
  }

  // Recovery + invite flows: verifyOtp issues a session so the user can set a
  // password. Route straight to the set-password page (no MFA gate — a freshly
  // invited user has none, and password-set must happen before app access).
  if (type === 'recovery' || type === 'invite') {
    return NextResponse.redirect(new URL(next, request.url));
  }

  const { data: aal, error: aalError } = await supabase.auth.mfa.getAuthenticatorAssuranceLevel();
  if (aalError) {
    // Fail closed: clear the session we just established and force re-auth.
    console.error('Confirm route: AAL check failed', aalError);
    await supabase.auth.signOut().catch((e) => {
      console.error('Confirm route: signOut after AAL failure also failed', e);
    });
    return NextResponse.redirect(new URL('/auth/login?error=mfa_check_failed', request.url));
  }
  if (aal.nextLevel === 'aal2' && aal.nextLevel !== aal.currentLevel) {
    return NextResponse.redirect(new URL('/auth/2fa', request.url));
  }

  return NextResponse.redirect(new URL(next, request.url));
}
