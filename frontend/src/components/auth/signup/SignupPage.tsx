'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useAuth } from '@/lib/hooks/useAuth';
import { RegisterForm } from '@/components/forms/auth/RegisterForm';
import SSOButtons from '@/components/auth/SSOButtons';
import { AuthMethodsDivider } from '@/components/auth/AuthMethodsDivider';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Checkbox } from '@/components/ui/checkbox';
import { Label } from '@/components/ui/label';
import type { RegisterData } from '@/lib/types/auth.types';

export function SignupPage() {
  const { register, loading, error } = useAuth();
  const [acceptedTerms, setAcceptedTerms] = useState(false);
  const [termsError, setTermsError] = useState('');
  const [ssoError, setSSOError] = useState<string | null>(null);

  const handleRegister = async (data: RegisterData) => {
    setTermsError('');
    if (!acceptedTerms) {
      const msg = 'You must accept the Terms of Service and Privacy Policy';
      setTermsError(msg);
      return { success: false, error: msg };
    }
    return register(data);
  };

  const surfaceError = ssoError ?? error ?? termsError;

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>Create your account</CardTitle>
        <CardDescription>Get started with email or your Google account.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {surfaceError && (
          <div className="p-3 text-sm text-destructive bg-destructive/10 border border-destructive/20 rounded-md">
            {surfaceError}
          </div>
        )}

        <SSOButtons onError={setSSOError} next="/app" />

        <AuthMethodsDivider label="or sign up with email" />

        <RegisterForm onSubmit={handleRegister} loading={loading} />

        <div className="flex items-start space-x-3">
          <Checkbox
            id="terms"
            checked={acceptedTerms}
            onCheckedChange={(checked) => setAcceptedTerms(checked as boolean)}
          />
          <Label htmlFor="terms" className="text-sm text-muted-foreground leading-none font-normal cursor-pointer">
            I agree to the{' '}
            <Link href="/terms" className="font-medium text-primary hover:text-primary/80 underline-offset-4 hover:underline" target="_blank">
              Terms of Service
            </Link>{' '}
            and{' '}
            <Link href="/privacy" className="font-medium text-primary hover:text-primary/80 underline-offset-4 hover:underline" target="_blank">
              Privacy Policy
            </Link>
          </Label>
        </div>

        <div className="text-center text-sm text-muted-foreground pt-2 border-t border-border/50">
          Already have an account?{' '}
          <Link href="/auth/login" className="font-medium text-primary hover:text-primary/80 transition-colors">
            Sign in
          </Link>
        </div>
      </CardContent>
    </Card>
  );
}
