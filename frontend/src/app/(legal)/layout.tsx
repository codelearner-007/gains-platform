import { Providers } from '@/components/common/Providers';
import { SiteNav } from '@/components/common/SiteNav';
import { SiteFooter } from '@/components/common/SiteFooter';

export default function LegalLayout({ children }: { children: React.ReactNode }) {
  return (
    <Providers>
      <div className="min-h-screen flex flex-col bg-background">
        <SiteNav />
        <main className="flex-1 pt-14">{children}</main>
        <SiteFooter />
      </div>
    </Providers>
  );
}
