'use client';

import {
  Card,
  CardHeader,
  CardTitle,
  CardDescription,
  CardContent,
} from '@/components/ui/card';
import { MFASetup } from '@/components/auth/mfa/MFASetup';
import { Shield, Smartphone, KeyRound, ScanLine } from 'lucide-react';

const howItWorks = [
  {
    icon: Smartphone,
    title: 'Install App',
    description:
      'Use Google Authenticator, Authy, or similar.',
  },
  {
    icon: ScanLine,
    title: 'Scan QR Code',
    description:
      'Link your account by scanning the code.',
  },
  {
    icon: KeyRound,
    title: 'Enter Code',
    description:
      'Enter the 6-digit verification code.',
  },
];

export function SecuritySection() {
  return (
    <div className="space-y-6">
      {/* 2FA setup card */}
      <Card className="border-border/50 shadow-sm">
        <CardHeader>
          <CardTitle className="text-lg">Two-Factor Authentication</CardTitle>
          <CardDescription>
            Add an extra layer of security to your account
          </CardDescription>
        </CardHeader>
        <CardContent>
          <MFASetup />
        </CardContent>
      </Card>

      {/* How it works */}
      <Card className="border-border/50 shadow-sm bg-muted/20">
        <CardHeader className="pb-3">
          <CardTitle className="text-base font-medium flex items-center gap-2">
            <Shield className="h-4 w-4 text-primary" />
            How It Works
          </CardTitle>
        </CardHeader>
        <CardContent>
          <div className="grid gap-4 sm:grid-cols-3">
            {howItWorks.map((step, i) => (
              <div key={i} className="flex flex-col gap-2 p-3 rounded-lg bg-background/50 border border-border/50">
                <div className="flex items-center gap-2">
                  <div className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-primary/10 text-primary text-xs font-bold">
                    {i + 1}
                  </div>
                  <step.icon className="h-4 w-4 text-muted-foreground" />
                </div>
                <div>
                  <p className="font-medium text-sm">{step.title}</p>
                  <p className="text-xs text-muted-foreground mt-1 leading-snug">
                    {step.description}
                  </p>
                </div>
              </div>
            ))}
          </div>
        </CardContent>
      </Card>
    </div>
  );
}
