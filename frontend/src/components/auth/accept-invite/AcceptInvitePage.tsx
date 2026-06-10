'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { useGlobal } from '@/lib/context/GlobalContext';
import { authService } from '@/lib/services/auth.service';
import { ResetPasswordForm } from '@/components/forms/auth/ResetPasswordForm';
import { useRouter } from 'next/navigation';
import { CheckCircle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

/**
 * Invite-acceptance page.
 *
 * Flow: the superadmin invites a user via `inviteUserByEmail`. The email links
 * to `/api/auth/confirm?type=invite&next=/auth/accept-invite`, which calls
 * `verifyOtp` server-side — that establishes the session (httpOnly cookies)
 * and redirects here. So by the time this page loads, the invited user already
 * has a session; they only need to SET a password.
 *
 * We confirm the session exists (`getCurrentUser`), then reuse the same
 * `resetPassword` machinery (`auth.updateUser({ password })`) to set it. On
 * success the user is fully logged in and lands in the app.
 */
export function AcceptInvitePage() {
  const { resetPassword, loading, error } = useAuth();
  const { setAuthFromLogin } = useGlobal();
  const [success, setSuccess] = useState(false);
  const [verifying, setVerifying] = useState(true);
  const [verificationError, setVerificationError] = useState('');
  const router = useRouter();

  // The session was established by /api/auth/confirm before redirecting here.
  // Confirm it's present so we can render the set-password form.
  useEffect(() => {
    const verifySession = async () => {
      try {
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

    verifySession();
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

        <ResetPasswordForm onSubmit={handleSubmit} loading={loading} />
      </CardContent>
    </Card>
  );
}
