'use client';

import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { authService } from '@/lib/services/auth.service';
import { useGlobal } from '@/lib/context/GlobalContext';
import { MFAVerification } from '@/components/auth/mfa/MFAVerification';
import { Card, CardContent } from '@/components/ui/card';
import { sanitizeReturnTo } from '@/lib/utils/return-to';

export function MFAVerificationPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const { refreshUser } = useGlobal();
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState('');

  const checkMFAStatus = useCallback(async () => {
    try {
      const status = await authService.getMFAStatus();

      // Redirect if user already verified (currentLevel aal2) OR has no MFA factors (nextLevel aal1)
      // - currentLevel === 'aal2': User already completed MFA verification this session
      // - nextLevel === 'aal1': User has no verified MFA factors, cannot achieve AAL2
      if (status.currentLevel === 'aal2' || status.nextLevel === 'aal1') {
        await refreshUser();
        const returnTo = sanitizeReturnTo(searchParams.get('returnTo'), '/app');
        router.push(returnTo);
        return;
      }

      setLoading(false);
    } catch (err) {
      if (err instanceof Error && err.message.includes('Unauthorized')) {
        router.push('/auth/login');
        return;
      }
      setError(err instanceof Error ? err.message : 'An error occurred');
      setLoading(false);
    }
  }, [refreshUser, router, searchParams]);

  useEffect(() => {
    void checkMFAStatus();
  }, [checkMFAStatus]);

  const handleVerified = useCallback(async () => {
    await refreshUser();
    const returnTo = sanitizeReturnTo(searchParams.get('returnTo'), '/app');
    router.push(returnTo);
  }, [refreshUser, router, searchParams]);

  if (loading) {
    return (
      <Card className="w-full max-w-md">
        <CardContent className="flex justify-center items-center p-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </CardContent>
      </Card>
    );
  }

  if (error) {
    return (
      <Card className="w-full max-w-md">
        <CardContent className="p-8">
          <div className="text-destructive text-center">{error}</div>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full max-w-md">
      <MFAVerification onVerified={handleVerified} />
    </Card>
  );
}
