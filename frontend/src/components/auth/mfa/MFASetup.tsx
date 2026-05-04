'use client';

import { useCallback, useEffect, useState } from 'react';
import { useMFA } from '@/lib/hooks/useMFA';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Key, CheckCircle, XCircle, Loader2 } from 'lucide-react';
import type { MFAFactorListItem } from '@/lib/types/auth.types';
import Image from 'next/image';

interface MFASetupProps {
  onStatusChange?: () => void;
}

export function MFASetup({ onStatusChange }: MFASetupProps) {
  const { listFactors, enrollFactor, challengeFactor, verifyFactor, unenrollFactor, loading } = useMFA();
  const [factors, setFactors] = useState<MFAFactorListItem[]>([]);
  const [step, setStep] = useState<'list' | 'name' | 'enroll'>('list');
  const [factorId, setFactorId] = useState('');
  const [qr, setQR] = useState('');
  const [verifyCode, setVerifyCode] = useState('');
  const [friendlyName, setFriendlyName] = useState('');
  const [error, setError] = useState('');
  const [initialLoading, setInitialLoading] = useState(true);

  const fetchFactors = useCallback(async () => {
    const result = await listFactors();
    if (result.success) {
      setFactors(result.factors);
    } else {
      setError(result.error || 'Failed to fetch MFA status');
    }
    setInitialLoading(false);
  }, [listFactors]);

  useEffect(() => {
    void fetchFactors();
  }, [fetchFactors]);

  const startEnrollment = async () => {
    if (!friendlyName.trim()) {
      setError('Please provide a name for this authentication method');
      return;
    }

    setError('');
    const result = await enrollFactor(friendlyName);

    if (result.success && result.factorId && result.qrCode) {
      setFactorId(result.factorId);
      setQR(result.qrCode);
      setStep('enroll');
    } else {
      setError(result.error || 'Failed to start MFA enrollment');
    }
  };

  const handleVerifyFactor = async () => {
    setError('');

    const challengeResult = await challengeFactor(factorId);
    if (!challengeResult.success || !challengeResult.challengeId) {
      setError(challengeResult.error || 'Failed to create challenge');
      return;
    }

    const verifyResult = await verifyFactor(factorId, challengeResult.challengeId, verifyCode);
    if (verifyResult.success) {
      await fetchFactors();
      resetEnrollment();
      onStatusChange?.();
    } else {
      setError(verifyResult.error || 'Failed to verify MFA code');
    }
  };

  const handleUnenrollFactor = async (id: string) => {
    setError('');
    const result = await unenrollFactor(id);

    if (result.success) {
      await fetchFactors();
      onStatusChange?.();
    } else {
      setError(result.error || 'Failed to unenroll MFA factor');
    }
  };

  const resetEnrollment = () => {
    setStep('list');
    setFactorId('');
    setQR('');
    setVerifyCode('');
    setFriendlyName('');
    setError('');
  };

  if (initialLoading) {
    return (
      <Card>
        <CardContent className="flex justify-center items-center p-6">
          <Loader2 className="h-6 w-6 animate-spin" />
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2">
          <Key className="h-5 w-5" />
          Two-Factor Authentication (2FA)
        </CardTitle>
        <CardDescription>
          Add an additional layer of security to your account
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {factors.length > 0 && step === 'list' && (
          <div className="space-y-4">
            {factors.map((factor) => (
              <div key={factor.id} className="flex items-center justify-between p-4 border border-border rounded-lg">
                <div className="flex items-center gap-3">
                  {factor.status === 'verified' ? (
                    <CheckCircle className="h-5 w-5 text-primary" />
                  ) : (
                    <XCircle className="h-5 w-5 text-destructive" />
                  )}
                  <div>
                    <p className="font-medium">
                      {factor.friendly_name || 'Authenticator App'}
                    </p>
                    <p className="text-sm text-muted-foreground">
                      Added on {new Date(factor.created_at).toLocaleDateString()}
                    </p>
                  </div>
                </div>
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() => handleUnenrollFactor(factor.id)}
                  disabled={loading}
                  className="text-destructive hover:text-destructive/90"
                >
                  Remove
                </Button>
              </div>
            ))}
          </div>
        )}

        {step === 'name' && (
          <div className="space-y-4">
            <div className="space-y-2">
              <Label htmlFor="friendly-name">
                Device Name
              </Label>
              <Input
                id="friendly-name"
                type="text"
                value={friendlyName}
                onChange={(e) => setFriendlyName(e.target.value)}
                placeholder="e.g., Work Phone, Personal iPhone"
                autoFocus
              />
              <p className="text-sm text-muted-foreground">
                Give this authentication method a name to help you identify it later
              </p>
            </div>

            <div className="flex justify-end space-x-3">
              <Button
                variant="outline"
                onClick={resetEnrollment}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button
                onClick={startEnrollment}
                disabled={loading || !friendlyName.trim()}
              >
                {loading ? 'Processing...' : 'Continue'}
              </Button>
            </div>
          </div>
        )}

        {step === 'enroll' && (
          <div className="space-y-4">
            <div className="flex justify-center">
              {qr && (
                <Image
                  src={qr}
                  alt="QR Code"
                  width={192}
                  height={192}
                  unoptimized
                  className="w-48 h-48 border border-border rounded-lg p-2"
                />
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="verify-code">
                Verification Code
              </Label>
              <Input
                id="verify-code"
                type="text"
                value={verifyCode}
                onChange={(e) => setVerifyCode(e.target.value.trim())}
                placeholder="Enter code from your authenticator app"
              />
            </div>

            <div className="flex justify-end space-x-3">
              <Button
                variant="outline"
                onClick={resetEnrollment}
                disabled={loading}
              >
                Cancel
              </Button>
              <Button
                onClick={handleVerifyFactor}
                disabled={loading || verifyCode.length === 0}
              >
                {loading ? 'Verifying...' : 'Verify'}
              </Button>
            </div>
          </div>
        )}

        {step === 'list' && (
          <div className="space-y-4">
            <p className="text-sm text-muted-foreground">
              {factors.length === 0
                ? 'Protect your account with two-factor authentication. When enabled, you\'ll need to enter a code from your authenticator app in addition to your password when signing in.'
                : 'You can add additional authentication methods or remove existing ones.'}
            </p>
            <Button
              onClick={() => setStep('name')}
              disabled={loading}
              className="w-full"
            >
              {loading ? 'Processing...' : 'Add New Authentication Method'}
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
}