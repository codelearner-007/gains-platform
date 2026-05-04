'use client';

import React, { useEffect, useState } from 'react';
import Link from 'next/link';
import { Shield, X } from 'lucide-react';
import { setCookie, getCookie } from 'cookies-next/client';
import { Button } from '@/components/ui/button';

const COOKIE_CONSENT_KEY = 'cookie-accept';
const COOKIE_EXPIRY_DAYS = 365;

export default function CookieConsent() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const consent = getCookie(COOKIE_CONSENT_KEY);
    if (consent) return;

    const timer = setTimeout(() => setIsVisible(true), 1000);
    return () => clearTimeout(timer);
  }, []);

  const setConsent = (value: 'accepted' | 'declined') => {
    setCookie(COOKIE_CONSENT_KEY, value, {
      expires: new Date(Date.now() + COOKIE_EXPIRY_DAYS * 24 * 60 * 60 * 1000),
      sameSite: 'strict',
      secure: process.env.NODE_ENV === 'production',
      path: '/',
    });
    setIsVisible(false);
  };

  if (!isVisible) return null;

  return (
    <div className="fixed bottom-0 left-0 right-0 bg-background border-t border-border shadow-lg z-50">
      <div className="max-w-7xl mx-auto px-4 py-4 sm:px-6 lg:px-8">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <div className="flex items-start gap-3">
            <Shield className="h-5 w-5 text-primary mt-0.5" />
            <div className="space-y-1">
              <p className="text-sm text-muted-foreground">
                We use cookies to enhance your browsing experience and analyze our traffic.
                By clicking &quot;Accept&quot;, you consent to our use of cookies. See our{' '}
                <Link href="/privacy" className="text-primary hover:underline underline-offset-4">
                  Privacy Policy
                </Link>{' '}
                and{' '}
                <Link href="/terms" className="text-primary hover:underline underline-offset-4">
                  Terms
                </Link>
                .
              </p>
            </div>
          </div>

          <div className="flex items-center gap-2">
            <Button variant="outline" size="sm" onClick={() => setConsent('declined')}>
              Decline
            </Button>
            <Button size="sm" onClick={() => setConsent('accepted')}>
              Accept
            </Button>
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setConsent('declined')}
              aria-label="Close"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </div>
      </div>
    </div>
  );
}

