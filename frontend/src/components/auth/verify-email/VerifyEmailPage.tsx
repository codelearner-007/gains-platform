'use client';

import { CheckCircle } from 'lucide-react';
import Link from 'next/link';
import { useState } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { authService } from '@/lib/services/auth.service';
import { ResendVerificationForm } from '@/components/forms/auth/ResendVerificationForm';

export function VerifyEmailPage() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState(false);

  const handleResend = async (data: { email: string }) => {
    try {
      setLoading(true);
      setError('');
      await authService.resendVerificationEmail(data.email);
      setSuccess(true);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'An unknown error occurred');
    } finally {
      setLoading(false);
    }
  };

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <div className="flex justify-center mb-2">
          <CheckCircle className="h-16 w-16 text-primary" />
        </div>
        <CardTitle>Check your email</CardTitle>
        <CardDescription>We&apos;ve sent you a verification link</CardDescription>
      </CardHeader>
      <CardContent>
        <div className="space-y-6">
          <p className="text-muted-foreground text-center">
            We&apos;ve sent you an email with a verification link.
            Please check your inbox and click the link to verify your account.
          </p>

          <div className="space-y-4">
            <p className="text-sm text-muted-foreground text-center">
              Didn&apos;t receive the email? Check your spam folder or enter your email to resend:
            </p>

            {error && (
              <Alert variant="destructive">
                <AlertDescription>{error}</AlertDescription>
              </Alert>
            )}

            {success && (
              <Alert className="border-primary/30 bg-primary/5">
                <AlertDescription className="text-primary">
                  Verification email has been resent successfully.
                </AlertDescription>
              </Alert>
            )}

            <ResendVerificationForm onSubmit={handleResend} loading={loading} />
          </div>

          <div className="pt-6 border-t border-border">
            <Link
              href="/auth/login"
              className="block text-center text-sm font-medium text-primary hover:text-primary/80 transition-colors"
            >
              Return to login
            </Link>
          </div>
        </div>
      </CardContent>
    </Card>
  );
}
