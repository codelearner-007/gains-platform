'use client';

import { useState } from 'react';
import { authService } from '@/lib/services/auth.service';
import { Button } from '@/components/ui/button';

type Provider = 'google';

interface SSOButtonsProps {
  onError?: (error: string) => void;
  /** Server-side allowlisted destination after sign-in. */
  next?: string;
  /** Whether the Google credential is configured on the server. */
  googleEnabled?: boolean;
}

const PROVIDER_CONFIGS: Record<Provider, { name: string; icon: React.ReactNode }> = {
  google: {
    name: 'Google',
    icon: (
      <svg viewBox="0 0 20 20" className="w-4 h-4">
        <path d="M19.6 10.23c0-.82-.1-1.42-.25-2.05H10v3.72h5.5c-.15.96-.74 2.31-2.04 3.22v2.45h3.16c1.89-1.73 2.98-4.3 2.98-7.34z" fill="#4285F4" />
        <path d="M10 20c2.67 0 4.9-.89 6.57-2.43l-3.16-2.45c-.89.59-2.01.96-3.41.96-2.61 0-4.83-1.76-5.63-4.13H1.07v2.51C2.72 17.75 6.09 20 10 20z" fill="#34A853" />
        <path d="M4.37 11.95c-.2-.6-.31-1.24-.31-1.95s.11-1.35.31-1.95V5.54H1.07C.38 6.84 0 8.36 0 10s.38 3.16 1.07 4.46l3.3-2.51z" fill="#FBBC05" />
        <path d="M10 3.98c1.48 0 2.79.51 3.83 1.5l2.78-2.78C14.93 1.03 12.7 0 10 0 6.09 0 2.72 2.25 1.07 5.54l3.3 2.51C5.17 5.68 7.39 3.98 10 3.98z" fill="#EA4335" />
      </svg>
    ),
  },
};

function parseProviders(): Provider[] {
  const raw = process.env.NEXT_PUBLIC_SSO_PROVIDERS || 'google';
  return raw
    .split(',')
    .map((p) => p.trim().toLowerCase())
    .filter((p): p is Provider => p in PROVIDER_CONFIGS);
}

export default function SSOButtons({ onError, next = '/app', googleEnabled = false }: SSOButtonsProps) {
  const [pending, setPending] = useState<Provider | null>(null);

  const handleSSOLogin = async (provider: Provider) => {
    if (pending) return;
    setPending(provider);
    try {
      await authService.signInWithOAuth(provider, next);
      // Browser is redirecting; intentionally don't reset pending.
    } catch (err: unknown) {
      const message = err instanceof Error ? err.message : 'Sign-in failed';
      onError?.(message);
      setPending(null);
    }
  };

  // Credential check AND the NEXT_PUBLIC_SSO_PROVIDERS allowlist must both pass.
  const enabled = googleEnabled ? parseProviders() : [];
  if (enabled.length === 0) return null;

  return (
    <div className="space-y-2">
      {enabled.map((provider) => {
        const config = PROVIDER_CONFIGS[provider];
        const isPending = pending === provider;
        return (
          <Button
            key={provider}
            type="button"
            variant="outline"
            size="lg"
            onClick={() => handleSSOLogin(provider)}
            disabled={!!pending}
            className="w-full justify-center gap-2"
          >
            {config.icon}
            <span>{isPending ? 'Redirecting…' : `Continue with ${config.name}`}</span>
          </Button>
        );
      })}
    </div>
  );
}
