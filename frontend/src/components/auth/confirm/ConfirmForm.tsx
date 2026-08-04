'use client';

import { useRef, useState } from 'react';
import { Button } from '@/components/ui/button';

/**
 * The single deliberate piece of client JS in the confirm flow.
 *
 * This is a NATIVE form POST (no preventDefault, no fetch), so the browser
 * submits it as a top-level navigation. That is exactly what makes it survive
 * email security scanners: they issue automated GETs and even run page-load
 * JavaScript, but they do not click buttons or submit forms, so the one-time
 * token (carried in the httpOnly cookie, not this page) is spent only when a
 * real person clicks.
 *
 * The JavaScript here does ONE thing: guard against a double-click spending the
 * single-use token twice. The ref blocks a second submit; the disabled state is
 * user feedback. With JavaScript disabled the form still submits once per click,
 * degrading to the same single-submit intent.
 */
export function ConfirmForm({ actionLabel }: { actionLabel: string }) {
  const [submitting, setSubmitting] = useState(false);
  const submittedRef = useRef(false);

  return (
    <form
      method="POST"
      action="/api/auth/confirm"
      onSubmit={(e) => {
        if (submittedRef.current) {
          e.preventDefault();
          return;
        }
        submittedRef.current = true;
        setSubmitting(true);
      }}
    >
      <Button type="submit" className="w-full" disabled={submitting}>
        {submitting ? 'Verifying…' : actionLabel}
      </Button>
    </form>
  );
}
