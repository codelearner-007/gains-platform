'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { useGlobal } from '@/lib/context/GlobalContext';
import { authService } from '@/lib/services/auth.service';
import { createSPAClient } from '@/lib/supabase/client';
import { ResetPasswordForm } from '@/components/forms/auth/ResetPasswordForm';
import { useRouter } from 'next/navigation';
import { CheckCircle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

/**
 * Invite-acceptance page.
 *
 * Flow: the superadmin invites a user via `inviteUserByEmail`. Supabase invite
 * emails use the implicit flow — clicking the link verifies the invite and
 * redirects here with the session in the URL HASH
 * (`#access_token=…&refresh_token=…&type=invite`), which the server never sees.
 * So we read those hash tokens and call `setSession` on the browser client;
 * @supabase/ssr persists the session to the auth cookies, giving the
 * subsequent server-side set-password call (`auth.updateUser`) a session.
 *
 * After the session is established we reuse the `resetPassword` machinery to
 * SET the password. On success the user is fully logged in and lands in the app.
 */
export function AcceptInvitePage() {
  const { resetPassword, loading, error } = useAuth();
  const { setAuthFromLogin } = useGlobal();
  const [success, setSuccess] = useState(false);
  const [verifying, setVerifying] = useState(true);
  const [verificationError, setVerificationError] = useState('');
  const router = useRouter();

  // Establish the session from the invite hash tokens (implicit flow), then
  // confirm it so we can render the set-password form.
  useEffect(() => {
    const acceptInvite = async () => {
      try {
        const rawHash =
          typeof window !== 'undefined'
            ? window.location.hash.replace(/^#/, '')
            : '';
        const hashParams = new URLSearchParams(rawHash);

        const linkError =
          hashParams.get('error_description') || hashParams.get('error');
        if (linkError) {
          throw new Error(linkError);
        }

        const accessToken = hashParams.get('access_token');
        const refreshToken = hashParams.get('refresh_token');
        if (accessToken && refreshToken) {
          const supabase = createSPAClient();
          const { error: sessionError } = await supabase.auth.setSession({
            access_token: accessToken,
            refresh_token: refreshToken,
          });
          if (sessionError) throw sessionError;
          // Strip the tokens from the URL so they don't linger in history.
          window.history.replaceState(
            null,
            '',
            window.location.pathname + window.location.search,
          );
        }

        const me = await authService.getCurrentUser();
        setAuthFromLogin({ user: me.user, mfaRequired: !!me.requiresMFA });
        setVerifying(false);
      } catch {
        setVerificationError(
          'This invitation link is invalid or has expired. Please ask your administrator to resend it.',
        );
        setVerifying(false);
      }
    };

    acceptInvite();
  }, [setAuthFromLogin]);

  const handleSubmit = async (data: { newPassword: string; confirmPassword: string }) => {
    const result = await resetPassword(data.newPassword, data.confirmPassword);
    if (result.success) {
      const requiresMFA =
        'requiresMFA' in result && typeof result.requiresMFA === 'boolean'
          ? result.requiresMFA
          : false;
      setSuccess(true);
      setTimeout(() => {
        router.push(requiresMFA ? '/auth/2fa?returnTo=/app' : '/app');
      }, 1500);
    }
  };

  if (verifying) {
    return (
      <Card className="w-full max-w-md">
        <CardContent className="pt-6">
          <div className="text-center">
            <div className="flex justify-center mb-4">
              <Loader2 className="h-12 w-12 text-primary animate-spin" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Verifying invitation
            </h2>
            <p className="text-muted-foreground">
              Please wait while we verify your invitation...
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (verificationError) {
    return (
      <Card className="w-full max-w-md">
        <CardContent className="pt-6">
          <div className="text-center">
            <div className="flex justify-center mb-4">
              <div className="h-12 w-12 rounded-full bg-destructive/10 flex items-center justify-center">
                <span className="text-2xl">⚠️</span>
              </div>
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Invitation invalid
            </h2>
            <p className="text-muted-foreground mb-6">{verificationError}</p>
            <Button
              onClick={() => router.push('/auth/login')}
              variant="outline"
              className="w-full"
            >
              Back to Sign In
            </Button>
          </div>
        </CardContent>
      </Card>
    );
  }

  if (success) {
    return (
      <Card className="w-full max-w-md">
        <CardContent className="pt-6">
          <div className="text-center">
            <div className="flex justify-center mb-4">
              <CheckCircle className="h-16 w-16 text-primary" />
            </div>
            <h2 className="text-2xl font-bold text-foreground mb-2">
              Welcome to GAINS
            </h2>
            <p className="text-muted-foreground mb-8">
              Your account is ready. You will be redirected in a moment.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Set your password</CardTitle>
        <CardDescription>
          Choose a password to finish setting up your account.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <div className="p-4 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg">
            {error}
          </div>
        )}

        <ResetPasswordForm
          onSubmit={handleSubmit}
          loading={loading}
          submitLabel="Set password"
          submittingLabel="Setting up your account…"
        />
      </CardContent>
    </Card>
  );
}
