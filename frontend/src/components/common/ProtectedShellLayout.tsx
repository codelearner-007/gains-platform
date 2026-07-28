import AppLayout from '@/components/common/AppLayout';
import { Providers } from '@/components/common/Providers';
import { SelectedSchoolProvider } from '@/lib/context/SelectedSchoolContext';
import { ReportsQueryClientProvider } from '@/lib/reports/query-client';
import { getIsFramed } from '@/lib/server/me';

export default async function ProtectedShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Inside the Schoology iframe (the `gains-framed` marker, set only by the LTI
  // bridge) the owner wants NO app chrome — no sidebar, header, logo, or nav.
  // Decided server-side so the bare shell renders on first paint (no flicker),
  // and NOT threaded through AppLayout. Standalone visits keep the full shell.
  const framed = await getIsFramed();

  const content = framed ? (
    <main className="min-h-screen bg-background p-6 lg:p-10">{children}</main>
  ) : (
    <AppLayout>{children}</AppLayout>
  );

  return (
    <Providers>
      <ReportsQueryClientProvider>
        <SelectedSchoolProvider>{content}</SelectedSchoolProvider>
      </ReportsQueryClientProvider>
    </Providers>
  );
}
