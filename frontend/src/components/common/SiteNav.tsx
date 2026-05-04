import Link from 'next/link';
import { Sparkles } from 'lucide-react';
import AuthAwareButtons from '@/components/common/AuthAwareButtons';
import { MobileNavToggle } from '@/components/common/MobileNavToggle';
import { ThemeToggle } from '@/components/ui/theme-toggle';
import { publicSettings } from '@/lib/core/public-settings';

export function SiteNav() {
  const productName = publicSettings.NEXT_PUBLIC_PRODUCTNAME;

  return (
    <nav className="fixed top-0 inset-x-0 z-50 surface-blur bg-background/70 border-b border-border/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-14 items-center">
          <Link href="/" className="flex items-center gap-2 group">
            <div className="h-7 w-7 rounded-md bg-foreground text-background flex items-center justify-center transition-transform group-hover:scale-105">
              <Sparkles className="h-3.5 w-3.5" />
            </div>
            <span className="text-sm font-semibold tracking-tight text-foreground">
              {productName}
            </span>
          </Link>
          <div className="hidden md:flex items-center gap-7">
            <Link
              href="/#features"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Features
            </Link>
            <Link
              href="/#workflow"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Workflow
            </Link>
            <Link
              href="/#stack"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Stack
            </Link>
            <Link
              href="/#architecture"
              className="text-sm text-muted-foreground hover:text-foreground transition-colors"
            >
              Architecture
            </Link>
            <div className="h-5 w-px bg-border" />
            <ThemeToggle />
            <AuthAwareButtons variant="nav" />
          </div>
          <MobileNavToggle>
            <Link href="/#features" className="block text-muted-foreground hover:text-foreground py-1">
              Features
            </Link>
            <Link href="/#workflow" className="block text-muted-foreground hover:text-foreground py-1">
              Workflow
            </Link>
            <Link href="/#stack" className="block text-muted-foreground hover:text-foreground py-1">
              Stack
            </Link>
            <Link href="/#architecture" className="block text-muted-foreground hover:text-foreground py-1">
              Architecture
            </Link>
            <div className="pt-2 border-t border-border flex flex-col gap-2">
              <AuthAwareButtons variant="nav" />
            </div>
          </MobileNavToggle>
        </div>
      </div>
    </nav>
  );
}
