import Link from 'next/link';
import AuthAwareButtons from '@/components/common/AuthAwareButtons';
import { BrandWordmark } from '@/components/common/BrandWordmark';
import { ScrollNavShell } from '@/components/common/ScrollNavShell';

export function SiteNav() {
  return (
    <nav className="fixed top-0 inset-x-0 z-50 surface-blur bg-background/70 border-b border-border/60">
      <ScrollNavShell>
        <div className="flex justify-between h-14 items-center">
          <Link href="/" className="flex items-center transition-opacity hover:opacity-80">
            <BrandWordmark height={26} priority />
          </Link>
          <div className="flex items-center gap-5 sm:gap-6">
            <div className="hidden sm:flex items-center gap-6">
              <Link href="/privacy" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                Privacy
              </Link>
              <Link href="/terms" className="text-sm text-muted-foreground hover:text-foreground transition-colors">
                Terms
              </Link>
            </div>
            <AuthAwareButtons variant="nav" />
          </div>
        </div>
      </ScrollNavShell>
    </nav>
  );
}
