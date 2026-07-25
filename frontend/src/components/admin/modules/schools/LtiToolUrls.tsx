'use client';

import { useEffect, useState } from 'react';
import { Check, Copy, Loader2 } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { getLtiToolUrls, type LtiToolUrls } from '@/lib/services/lti.service';

interface CopyRowProps {
  label: string;
  value: string;
}

function CopyRow({ label, value }: CopyRowProps) {
  const [copied, setCopied] = useState(false);

  const onCopy = async () => {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      // Clipboard blocked (insecure context / permissions) — no-op; the value
      // is on screen and selectable, so the admin can still copy manually.
    }
  };

  return (
    <div className="space-y-1">
      <Label className="text-xs text-muted-foreground">{label}</Label>
      <div className="flex items-center gap-2">
        <code className="min-w-0 flex-1 truncate rounded-md border border-border bg-muted px-2 py-1.5 text-xs text-foreground">
          {value}
        </code>
        <Button
          type="button"
          variant="outline"
          size="sm"
          className="shrink-0"
          onClick={onCopy}
          aria-label={`Copy ${label}`}
        >
          {copied ? (
            <Check className="h-3.5 w-3.5 text-success" />
          ) : (
            <Copy className="h-3.5 w-3.5" />
          )}
        </Button>
      </div>
    </div>
  );
}

/**
 * Read-only panel showing the three tool URLs (and the tool kid once bound) to
 * hand back to the district's Schoology app. Fetches GET /admin/lti/tool-urls.
 * ``toolKid`` from the current binding is passed in so it reflects this school.
 */
export function LtiToolUrls({ toolKid }: { toolKid?: string | null }) {
  const [urls, setUrls] = useState<LtiToolUrls | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let active = true;
    getLtiToolUrls()
      .then((data) => {
        if (active) setUrls(data);
      })
      .catch(() => {
        // Non-fatal for the dialog; the binding editor still works.
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, []);

  if (loading) {
    return (
      <div className="flex items-center gap-2 py-2 text-sm text-muted-foreground">
        <Loader2 className="h-4 w-4 animate-spin" />
        Loading tool URLs…
      </div>
    );
  }
  if (!urls) return null;

  return (
    <div className="space-y-3 rounded-md border border-border bg-card p-3">
      <p className="text-xs text-muted-foreground">
        Give these three URLs to the district to configure the GAINS app in
        Schoology.
      </p>
      <CopyRow label="OIDC Login Init URL" value={urls.login_init} />
      <CopyRow label="Launch (Redirect) URL" value={urls.launch} />
      <CopyRow label="Public JWKS URL" value={urls.jwks} />
      {toolKid && <CopyRow label="Tool Key ID" value={toolKid} />}
      <p className="text-xs text-muted-foreground">
        Recommended launch presentation:{' '}
        <span className="font-medium text-foreground">new window / new tab</span>.
        This avoids third-party-cookie blocking that can occur when the dashboard
        is embedded in an iframe. Embedded (iframe) launch is supported but should
        be verified on the district&apos;s browsers first.
      </p>
    </div>
  );
}
