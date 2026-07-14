'use client';

import { useState, useId } from 'react';
import { Mail, KeyRound } from 'lucide-react';
import { useAuth } from '@/lib/hooks/useAuth';
import { LoginForm } from '@/components/forms/auth/LoginForm';
import SSOButtons from '@/components/auth/SSOButtons';
import { AuthMethodsDivider } from '@/components/auth/AuthMethodsDivider';
import { MagicLinkForm } from '@/components/auth/MagicLinkForm';
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from '@/components/ui/card';
import { cn } from '@/lib/utils';

type EmailMethod = 'password' | 'magic';

interface LoginPageProps {
  /** Whether Google sign-in is configured on the server; gates the SSO block. */
  googleEnabled: boolean;
}

export function LoginPage({ googleEnabled }: LoginPageProps) {
  const { login, loading, error } = useAuth();
  const [ssoError, setSSOError] = useState<string | null>(null);
  const [method, setMethod] = useState<EmailMethod>('password');
  const tablistId = useId();
  const passwordPanelId = `${tablistId}-password`;
  const magicPanelId = `${tablistId}-magic`;
  const passwordTabId = `${tablistId}-tab-password`;
  const magicTabId = `${tablistId}-tab-magic`;
  const surfaceError = ssoError ?? error;

  return (
    <Card className="w-full">
      <CardHeader className="space-y-1.5">
        <CardTitle className="text-xl">Welcome back</CardTitle>
        <CardDescription>Sign in to continue to your dashboard.</CardDescription>
      </CardHeader>
      <CardContent className="space-y-5">
        {surfaceError && (
          <div
            role="alert"
            aria-live="polite"
            className="rounded-md border border-destructive/30 bg-destructive/5 px-3 py-2 text-xs text-destructive"
          >
            {surfaceError}
          </div>
        )}

        {/* Google sign-in, shown only when the credential is configured. */}
        {googleEnabled && (
          <>
            <SSOButtons onError={setSSOError} next="/app" googleEnabled={googleEnabled} />
            <AuthMethodsDivider label="or continue with" />
          </>
        )}

        {/* Segmented switch: Password ↔ Magic Link. */}
        <div
          role="tablist"
          aria-label="Email sign-in method"
          className="grid grid-cols-2 gap-1 rounded-lg border border-border bg-muted/40 p-1"
        >
          <MethodTab
            id={passwordTabId}
            controls={passwordPanelId}
            active={method === 'password'}
            onClick={() => setMethod('password')}
            icon={<KeyRound className="h-3.5 w-3.5" />}
            label="Password"
          />
          <MethodTab
            id={magicTabId}
            controls={magicPanelId}
            active={method === 'magic'}
            onClick={() => setMethod('magic')}
            icon={<Mail className="h-3.5 w-3.5" />}
            label="Magic Link"
          />
        </div>

        <div
          role="tabpanel"
          id={passwordPanelId}
          aria-labelledby={passwordTabId}
          hidden={method !== 'password'}
        >
          {method === 'password' && <LoginForm onSubmit={login} loading={loading} />}
        </div>

        <div
          role="tabpanel"
          id={magicPanelId}
          aria-labelledby={magicTabId}
          hidden={method !== 'magic'}
        >
          {method === 'magic' && <MagicLinkForm />}
        </div>

        <div className="border-t border-border/60 pt-4 text-center text-sm text-muted-foreground">
          Access is by invitation only. Contact your administrator if you need an account.
        </div>
      </CardContent>
    </Card>
  );
}

interface MethodTabProps {
  id: string;
  controls: string;
  active: boolean;
  onClick: () => void;
  icon: React.ReactNode;
  label: string;
}

function MethodTab({ id, controls, active, onClick, icon, label }: MethodTabProps) {
  return (
    <button
      id={id}
      type="button"
      role="tab"
      aria-selected={active}
      aria-controls={controls}
      tabIndex={active ? 0 : -1}
      onClick={onClick}
      className={cn(
        'inline-flex items-center justify-center gap-1.5 rounded-md px-3 py-1.5 text-xs font-medium transition-all duration-150 ease-out',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
        active
          ? 'bg-card text-foreground shadow-sm border border-border'
          : 'text-muted-foreground hover:text-foreground',
      )}
    >
      {icon}
      {label}
    </button>
  );
}
