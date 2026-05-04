'use client';

import { useCallback, useEffect, useState } from 'react';
import { useMFA } from '@/lib/hooks/useMFA';
import { Card, CardHeader, CardTitle, CardDescription, CardContent } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { CheckCircle, Smartphone, Loader2 } from 'lucide-react';
import type { MFAFactorListItem } from '@/lib/types/auth.types';
import { cn } from '@/lib/utils';

interface MFAVerificationProps {
  onVerified: () => void;
}

export function MFAVerification({ onVerified }: MFAVerificationProps) {
  const { listFactors, challengeFactor, verifyFactor, loading } = useMFA();
  const [verifyCode, setVerifyCode] = useState('');
  const [error, setError] = useState('');
  const [factors, setFactors] = useState<MFAFactorListItem[]>([]);
  const [selectedFactorId, setSelectedFactorId] = useState<string>('');
  const [loadingFactors, setLoadingFactors] = useState(true);

  const loadFactorsData = useCallback(async () => {
    const result = await listFactors();
    if (result.success) {
      const totpFactors = result.totp;
      setFactors(totpFactors);

      // If there's only one factor, select it automatically
      if (totpFactors.length === 1) {
        setSelectedFactorId(totpFactors[0].id);
      }
    } else {
      setError(result.error || 'Failed to load authentication devices');
    }
    setLoadingFactors(false);
  }, [listFactors]);

  useEffect(() => {
    void loadFactorsData();
  }, [loadFactorsData]);

  const handleVerification = async () => {
    if (!selectedFactorId) {
      setError('Please select an authentication device');
      return;
    }

    setError('');

    const challengeResult = await challengeFactor(selectedFactorId);
    if (!challengeResult.success || !challengeResult.challengeId) {
      setError(challengeResult.error || 'Failed to create challenge');
      return;
    }

    const verifyResult = await verifyFactor(selectedFactorId, challengeResult.challengeId, verifyCode);
    if (verifyResult.success) {
      onVerified();
    } else {
      setError(verifyResult.error || 'Failed to verify MFA code');
    }
  };

  if (loadingFactors) {
    return (
      <Card className="w-full">
        <CardContent className="flex justify-center items-center py-8">
          <Loader2 className="h-8 w-8 animate-spin" />
        </CardContent>
      </Card>
    );
  }

  if (factors.length === 0) {
    return (
      <Card className="w-full">
        <CardContent className="py-8">
          <Alert variant="destructive">
            <AlertDescription>
              No authentication devices found. Please contact support.
            </AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card className="w-full">
      <CardHeader>
        <CardTitle>Two-Factor Authentication Required</CardTitle>
        <CardDescription>
          Please enter the verification code from your authenticator app
        </CardDescription>
      </CardHeader>
      <CardContent>
        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        <div className="space-y-4">
          {factors.length > 1 && (
            <div className="space-y-2">
              <Label>
                Select Authentication Device
              </Label>
              <div className="grid gap-3">
                {factors.map((factor) => (
                  <Button
                    key={factor.id}
                    type="button"
                    variant="outline"
                    onClick={() => setSelectedFactorId(factor.id)}
                    className={cn(
                      'h-auto justify-start gap-3 px-3 py-3 rounded-lg transition-colors',
                      selectedFactorId === factor.id
                        ? 'border-primary bg-primary/10 text-primary hover:bg-primary/15'
                        : 'hover:border-primary/50 hover:bg-muted'
                    )}
                  >
                    <Smartphone className="h-5 w-5" />
                    <div className="flex-1 text-left">
                      <p className="font-medium">
                        {factor.friendly_name || 'Authenticator Device'}
                      </p>
                      <p className="text-sm text-muted-foreground">
                        Added on {new Date(factor.created_at).toLocaleDateString()}
                      </p>
                    </div>
                    {selectedFactorId === factor.id && (
                      <CheckCircle className="h-5 w-5 text-primary" />
                    )}
                  </Button>
                ))}
              </div>
            </div>
          )}

          <div className="space-y-2">
            <Label>
              Verification Code
            </Label>
            <Input
              type="text"
              value={verifyCode}
              onChange={(e) => setVerifyCode(e.target.value.trim())}
              placeholder="Enter 6-digit code"
              maxLength={6}
            />
            <p className="text-sm text-muted-foreground">
              Enter the 6-digit code from your authenticator app
            </p>
          </div>

          <Button
            onClick={handleVerification}
            disabled={loading || verifyCode.length !== 6 || !selectedFactorId}
            className="w-full"
          >
            {loading ? 'Verifying...' : 'Verify'}
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}