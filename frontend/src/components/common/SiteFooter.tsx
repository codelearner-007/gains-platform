import Link from 'next/link';
import { BrandWordmark } from '@/components/common/BrandWordmark';

export function SiteFooter() {
  const year = new Date().getFullYear();

  return (
    <footer className="border-t border-border bg-background">
      <div className="max-w-7xl mx-auto py-8 px-6">
        <div className="flex flex-col sm:flex-row items-center justify-between gap-4">
          <Link href="/" className="flex items-center transition-opacity hover:opacity-80">
            <BrandWordmark height={22} />
          </Link>

          <div className="flex flex-col sm:flex-row items-center gap-x-6 gap-y-2 text-xs text-muted-foreground">
            <p>
              © {year} GAINS. A product of{' '}
              <a
                href="https://edvancelearning.us/"
                rel="noopener noreferrer"
                className="hover:text-foreground transition-colors"
              >
                Edvance Learning
              </a>
              .
            </p>
            <div className="flex items-center gap-6">
              <Link href="/privacy" className="hover:text-foreground transition-colors">
                Privacy
              </Link>
              <Link href="/terms" className="hover:text-foreground transition-colors">
                Terms
              </Link>
            </div>
          </div>
        </div>
      </div>
    </footer>
  );
}
