'use client';

import { useState } from 'react';
import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { useUser } from '@/lib/hooks/useUser';
import { ChangePasswordForm } from '@/components/forms/user/ChangePasswordForm';
import {
  CheckCircle,
  AlertCircle,
  Key,
  ShieldCheck,
  Lock,
  RefreshCw,
} from 'lucide-react';
import type { PasswordChangeInput } from '@/lib/schemas/user.schema';

const securityTips = [
  {
    icon: Lock,
    text: 'Use at least 8 characters with a mix of letters, numbers, and symbols',
  },
  {
    icon: RefreshCw,
    text: 'Change your password regularly and avoid reusing old passwords',
  },
  {
    icon: ShieldCheck,
    text: 'Enable two-factor authentication for additional account protection',
  },
];

export function PasswordSection() {
  const { changePassword, loading, error } = useUser();
  const [success, setSuccess] = useState(false);

  const handleSubmit = async (data: PasswordChangeInput) => {
    setSuccess(false);
    const result = await changePassword(data);

    if (result.success) {
      setSuccess(true);
      setTimeout(() => setSuccess(false), 5000);
    }

    return result;
  };

  return (
    <div className="space-y-6">
      {success && (
        <Alert className="border-primary/30 bg-primary/5 text-primary">
          <CheckCircle className="h-4 w-4" />
          <AlertDescription>
            Password changed successfully! Other sessions have been signed out.
          </AlertDescription>
        </Alert>
      )}

      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Password change card */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg">Change Password</CardTitle>
          <CardDescription>
            Update your password to keep your account secure
          </CardDescription>
        </CardHeader>
        <CardContent>
          <div className="max-w-md">
            <ChangePasswordForm onSubmit={handleSubmit} loading={loading} />
          </div>
        </CardContent>
      </Card>

      {/* Security tips */}
      <Card className="border-border/50 shadow-sm bg-muted/20">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium flex items-center gap-2">
            <ShieldCheck className="h-4 w-4 text-primary" />
            Password Best Practices
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-3">
            {securityTips.map((tip, i) => (
              <div key={i} className="flex flex-col gap-2 p-3 rounded-lg bg-background/50 border border-border/50">
                <tip.icon className="h-5 w-5 text-muted-foreground" />
                <p className="text-sm text-muted-foreground leading-snug">
                  {tip.text}
                </p>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
