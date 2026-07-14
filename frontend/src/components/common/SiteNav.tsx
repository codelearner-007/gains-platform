import Link from 'next/link';
import AuthAwareButtons from '@/components/common/AuthAwareButtons';
import { BrandWordmark } from '@/components/common/BrandWordmark';
import { ThemeToggle } from '@/components/ui/theme-toggle';

export function SiteNav() {
  return (
    <nav className="fixed top-0 inset-x-0 z-50 surface-blur bg-background/70 border-b border-border/60">
      <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8">
        <div className="flex justify-between h-14 items-center">
          <Link href="/" className="flex items-center transition-opacity hover:opacity-80">
            <BrandWordmark height={26} priority />
          </Link>
          <div className="flex items-center gap-3 sm:gap-4">
            <ThemeToggle />
            <AuthAwareButtons variant="nav" />
          </div>
        </div>
      </div>
    </nav>
  );
}
