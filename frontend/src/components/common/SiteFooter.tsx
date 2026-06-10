import React from 'react';
import Link from 'next/link';
import { Github, Sparkles } from 'lucide-react';
import { publicSettings } from '@/lib/core/public-settings';

export function SiteFooter() {
  const productName = publicSettings.NEXT_PUBLIC_PRODUCTNAME;

  return (
    <footer className="border-t border-border bg-background">
      <div className="max-w-7xl mx-auto py-12 px-6">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-10">
          <div className="space-y-3">
            <Link href="/" className="flex items-center gap-2">
              <div className="h-7 w-7 rounded-md bg-foreground text-background flex items-center justify-center">
                <Sparkles className="h-3.5 w-3.5" />
              </div>
              <span className="text-sm font-semibold tracking-tight">{productName}</span>
            </Link>
            <p className="text-sm text-muted-foreground max-w-xs leading-relaxed">
              A production-ready SaaS starter built with Next.js, FastAPI, and Supabase.
            </p>
          </div>

          <div>
            <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-3">
              Product
            </h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/#features" className="text-muted-foreground hover:text-foreground transition-colors">
                  Features
                </Link>
              </li>
              <li>
                <Link href="/#workflow" className="text-muted-foreground hover:text-foreground transition-colors">
                  Workflow
                </Link>
              </li>
              <li>
                <Link href="/#stack" className="text-muted-foreground hover:text-foreground transition-colors">
                  Stack
                </Link>
              </li>
              <li>
                <Link href="/#architecture" className="text-muted-foreground hover:text-foreground transition-colors">
                  Architecture
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-3">
              Get started
            </h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/auth/login" className="text-muted-foreground hover:text-foreground transition-colors">
                  Sign in
                </Link>
              </li>
            </ul>
          </div>

          <div>
            <h4 className="text-xs font-medium uppercase tracking-wider text-muted-foreground mb-3">
              Legal
            </h4>
            <ul className="space-y-2 text-sm">
              <li>
                <Link href="/privacy" className="text-muted-foreground hover:text-foreground transition-colors">
                  Privacy Policy
                </Link>
              </li>
              <li>
                <Link href="/terms" className="text-muted-foreground hover:text-foreground transition-colors">
                  Terms of Service
                </Link>
              </li>
            </ul>
          </div>
        </div>

        <div className="mt-12 pt-6 border-t border-border flex flex-col md:flex-row items-center justify-between gap-3">
          <p className="text-xs text-muted-foreground">
            © {new Date().getFullYear()} {productName} · MIT licensed
          </p>
          <Link
            href="https://github.com/"
            target="_blank"
            rel="noopener noreferrer"
            aria-label="GitHub"
            className="text-muted-foreground hover:text-foreground transition-colors"
          >
            <Github className="h-4 w-4" />
          </Link>
        </div>
      </div>
    </footer>
  );
}
