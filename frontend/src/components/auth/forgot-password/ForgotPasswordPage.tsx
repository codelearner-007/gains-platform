'use client';

import { useState } from 'react';
import { useAuth } from '@/lib/hooks/useAuth';
import { ForgotPasswordForm } from '@/components/forms/auth/ForgotPasswordForm';
import Link from 'next/link';
import { CheckCircle } from 'lucide-react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';

export function ForgotPasswordPage() {
  const { forgotPassword, loading, error } = useAuth();
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (data: { email: string }) => {
    const result = await forgotPassword(data.email);
    if (result.success) {
      setSuccess(true);
    }
  };

  if (success) {
    return (
      <Card className="w-full max-w-md">
        <CardContent className="pt-6">
          <div className="text-center">
            <div className="flex justify-center mb-4">
              <CheckCircle className="h-16 w-16 text-primary" />
            </div>

            <h2 className="text-2xl font-bold text-foreground mb-2">
              Check your email
            </h2>

            <p className="text-muted-foreground mb-8">
              We have sent a password reset link to your email address.
              Please check your inbox and follow the instructions to reset your password.
            </p>

            <Link href="/auth/login" className="font-medium text-primary hover:text-primary/80 transition-colors">
              Return to login
            </Link>
          </div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <CardHeader>
        <CardTitle>Reset your password</CardTitle>
        <CardDescription>Enter your email to receive a password reset link</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {error && (
          <div className="p-4 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-lg">
            {error}
          </div>
        )}

        <ForgotPasswordForm onSubmit={handleSubmit} loading={loading} />

        <div className="text-center text-sm text-muted-foreground">
          Remember your password?{' '}
          <Link href="/auth/login" className="font-medium text-primary hover:text-primary/80 transition-colors">
            Sign in
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
