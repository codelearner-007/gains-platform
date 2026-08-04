import type { Metadata } from 'next';
import Link from 'next/link';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ConfirmForm } from '@/components/auth/confirm/ConfirmForm';
import { isConfirmType, type ConfirmType } from '@/lib/auth/confirm-params';

export const metadata: Metadata = {
  title: 'Confirm',
};

/**
 * Interstitial confirm page (the human gate).
 *
 * The email link goes to the /api/auth/confirm route, which stashes the one-time
 * token in an httpOnly cookie and redirects here with only a (non-sensitive)
 * `type`. This page therefore never sees the token: it just renders a branded
 * card with a button that POSTs to /api/auth/confirm. A scanner that prefetches
 * the link lands here on static HTML and never submits the form, so the token is
 * not spent until a real person clicks. See ConfirmForm for why a native POST is
 * scanner-safe.
 */

// Presentational copy per confirm type. Lives with the page (its only consumer);
// the shared logic (which types exist, where they forward) is in confirm-params.
const TYPE_UI: Record<ConfirmType, { title: string; description: string; action: string }> = {
  invite: {
    title: 'Accept your invitation',
    description: 'Confirm below to set up your GAINS account.',
    action: 'Accept invitation',
  },
  recovery: {
    title: 'Reset your password',
    description: 'Confirm below to choose a new password.',
    action: 'Reset password',
  },
  magiclink: {
    title: 'Sign in to GAINS',
    description: 'Confirm below to finish signing in.',
    action: 'Sign in',
  },
  email_change: {
    title: 'Confirm your email change',
    description: 'Confirm below to update the email on your account.',
    action: 'Confirm email change',
  },
  email: {
    title: 'Confirm your email',
    description: 'Confirm below to verify your email address.',
    action: 'Confirm email',
  },
};

type ErrorView = { title: string; description: string; href: string; label: string };

/**
 * Error state shown for a malformed link or a failed verify (status=invalid,
 * redirected here by the route). Supabase cannot tell an expired token from an
 * already-used one, so the copy never claims to know which; it just points at
 * the right way to get a fresh link.
 */
function buildErrorView(type: ConfirmType | null, failed: boolean): ErrorView {
  if (!type) {
    return {
      title: 'This link is not available',
      description:
        'This link is missing information or is no longer valid. Ask for a new one and try again.',
      href: '/auth/login',
      label: 'Go to sign in',
    };
  }

  const state = failed ? 'has already been used or has expired' : 'is no longer valid';

  switch (type) {
    case 'invite':
      return {
        title: 'This invitation is not available',
        description: `This invitation link ${state}. If you have already set your password, sign in below. Otherwise, ask your administrator to resend the invitation.`,
        href: '/auth/login',
        label: 'Go to sign in',
      };
    case 'recovery':
      return {
        title: 'This reset link is not available',
        description: `This password reset link ${state}. Request a new one below.`,
        href: '/auth/forgot-password',
        label: 'Request a new reset link',
      };
    case 'magiclink':
      return {
        title: 'This sign-in link is not available',
        description: `This sign-in link ${state}. Request a new one below.`,
        href: '/auth/login',
        label: 'Request a new sign-in link',
      };
    default:
      return {
        title: 'This link is not available',
        description: `This link ${state}. Ask for a new one and try again.`,
        href: '/auth/login',
        label: 'Go to sign in',
      };
  }
}

export default async function ConfirmPage({
  searchParams,
}: {
  searchParams: Promise<{ type?: string; status?: string }>;
}) {
  const params = await searchParams;
  const type = isConfirmType(params.type) ? params.type : null;
  const failed = params.status === 'invalid';

  // Error card: a verify that failed upstream, or a link with no usable type.
  // Never renders a form. Same branded card, type-aware recovery path.
  if (failed || !type) {
    const view = buildErrorView(type, failed);
    return (
      <Card className="w-full max-w-md">
        <CardHeader>
          <CardTitle>{view.title}</CardTitle>
          <CardDescription>{view.description}</CardDescription>
        </CardHeader>
        <CardContent>
          <Button asChild variant="outline" className="w-full">
            <Link href={view.href}>{view.label}</Link>
          </Button>
        </CardContent>
      </Card>
    );
  }

  const ui = TYPE_UI[type];

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>{ui.title}</CardTitle>
        <CardDescription>{ui.description}</CardDescription>
      </CardHeader>
      <CardContent>
        <ConfirmForm actionLabel={ui.action} />
      </CardContent>
    </Card>
  );
}
