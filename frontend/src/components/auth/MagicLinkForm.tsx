'use client';

import { useState } from 'react';
import { z } from 'zod';
import { Mail, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { authService } from '@/lib/services/auth.service';

const emailSchema = z.string().email('Enter a valid email address').max(254);

export function MagicLinkForm() {
  const [email, setEmail] = useState('');
  const [status, setStatus] = useState<'idle' | 'pending' | 'sent' | 'error'>('idle');
  const [errorMessage, setErrorMessage] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault();
    if (status === 'pending') return;
    setErrorMessage(null);

    const parsed = emailSchema.safeParse(email.trim());
    if (!parsed.success) {
      setStatus('error');
      setErrorMessage(parsed.error.issues[0]?.message ?? 'Invalid email');
      return;
    }

    setStatus('pending');
    try {
      const result = await authService.sendMagicLink(parsed.data);
      setStatus('sent');
      setErrorMessage(result.message);
    } catch (err) {
      // Treat all server failures the same as success to preserve the
      // anti-enumeration guarantee: a probing attacker should not be able to
      // distinguish "valid email + rate-limited" from "no such account" or
      // "valid email + sent". Log the real error for ops visibility.
      console.error('sendMagicLink failed', err);
      setStatus('sent');
      setErrorMessage('If that email is registered, a sign-in link has been sent.');
    }
  };

  if (status === 'sent') {
    return (
      <div className="rounded-md border border-success/30 bg-success/5 p-3 text-sm text-success-foreground">
        <p className="text-success font-medium flex items-center gap-2">
          <Mail className="h-4 w-4" />
          Check your inbox
        </p>
        <p className="mt-1 text-xs text-muted-foreground">
          {errorMessage}
        </p>
        <button
          type="button"
          className="mt-2 text-xs text-primary hover:underline underline-offset-4"
          onClick={() => {
            setStatus('idle');
            setEmail('');
            setErrorMessage(null);
          }}
        >
          Send to a different email
        </button>
      </div>
    );
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3" noValidate>
      <div className="space-y-1.5">
        <Label htmlFor="magic-link-email" className="text-xs font-medium text-muted-foreground">
          Email for sign-in link
        </Label>
        <Input
          id="magic-link-email"
          type="email"
          placeholder="you@example.com"
          autoComplete="email"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          disabled={status === 'pending'}
          required
        />
      </div>
      {status === 'error' && errorMessage && (
        <p className="text-xs text-destructive">{errorMessage}</p>
      )}
      <Button type="submit" variant="default" size="lg" className="w-full" disabled={status === 'pending'}>
        {status === 'pending' ? (
          <>
            <Loader2 className="h-4 w-4 animate-spin" /> Sending link…
          </>
        ) : (
          <>
            <Mail className="h-4 w-4" />
            Email me a sign-in link
          </>
        )}
      </Button>
    </form>
  );
}
