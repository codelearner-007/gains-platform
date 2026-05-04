'use client';

import { useState, useEffect } from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { useGlobal } from '@/lib/context/GlobalContext';
import { authService } from '@/lib/services/auth.service';
import { ResetPasswordForm } from '@/components/forms/auth/ResetPasswordForm';
import { useRouter, useSearchParams } from 'next/navigation';
import { CheckCircle, Loader2 } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';

export function ResetPasswordPage() {
  const { resetPassword, loading, error } = useAuth();
  const { setAuthFromLogin } = useGlobal();
  const [success, setSuccess] = useState(false);
  const [verifying, setVerifying] = useState(true);
  const [verificationError, setVerificationError] = useState('');
  const [requiresMFA, setRequiresMFA] = useState(false);
  const router = useRouter();
  const searchParams = useSearchParams();

  // Verify the reset code from URL on mount
  useEffect(() => {
    const code = searchParams.get('code');

    if (!code) {
      setVerificationError('Invalid or missing reset code. Please request a new password reset link.');
      setVerifying(false);
      return;
    }

    // Exchange code for session
    const exchangeCode = async () => {
      try {
        await authService.exchangeCodeForSession(code);

        // Load current user immediately so GlobalContext is correct even though it only auto-loads once.
        // This ensures the app navbar won't show "Guest" after reset completes.
        try {
          const me = await authService.getCurrentUser();
          const mfa = !!me.requiresMFA;
          setRequiresMFA(mfa);
          setAuthFromLogin({ user: me.user, mfaRequired: mfa });
        } catch {
          // Non-fatal: user can still reset password; GlobalContext can refresh later if needed.
        }

        setVerifying(false);
      } catch {
        setVerificationError('Invalid or expired reset link. Please request a new password reset.');
        setVerifying(false);
      }
    };

    exchangeCode();
  }, [searchParams, setAuthFromLogin]);

  const handleSubmit = async (data: { newPassword: string; confirmPassword: string }) => {
    const result = await resetPassword(data.newPassword, data.confirmPassword);
    if (result.success) {
      const nextRequiresMFA =
        'requiresMFA' in result && typeof result.requiresMFA === 'boolean'
          ? result.requiresMFA
          : requiresMFA;

      setRequiresMFA(nextRequiresMFA);
      setSuccess(true);
      setTimeout(() => {
        router.push(nextRequiresMFA ? '/auth/2fa?returnTo=/app' : '/app');
      }, 1500);
    }
  };

  // Show loading while verifying the reset code
  if (verifying) {
    return (
      <Card className="w-full max-w-md">
        <CardContent className="pt-6">
          <div className="text-center">
            <div className="flex justify-center mb-4">
              <Loader2 className="h-12 w-12 text-primary animate-spin" />
            </div>
            <h2 className="text-xl font-semibold text-foreground mb-2">
              Verifying reset link
            </h2>
            <p className="text-muted-foreground">
              Please wait while we verify your password reset link...
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  // Show error if verification failed
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
              Verification Failed
            </h2>
            <p className="text-muted-foreground mb-6">
              {verificationError}
            </p>
            <Button
              onClick={() => router.push('/auth/forgot-password')}
              variant="outline"
              className="w-full"
            >
              Request New Reset Link
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
              Password reset successful
            </h2>

            <p className="text-muted-foreground mb-8">
              Your password has been successfully reset.
              You will be redirected to the app in a moment.
            </p>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Create new password</CardTitle>
        <CardDescription>Enter your new password below</CardDescription>
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
