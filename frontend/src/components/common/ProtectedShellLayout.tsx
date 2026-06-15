import AppLayout from '@/components/common/AppLayout';
import { Providers } from '@/components/common/Providers';
import { SelectedSchoolProvider } from '@/lib/context/SelectedSchoolContext';
import { ReportsQueryClientProvider } from '@/lib/reports/query-client';

export default function ProtectedShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Providers>
      <ReportsQueryClientProvider>
        <SelectedSchoolProvider>
          <AppLayout>{children}</AppLayout>
        </SelectedSchoolProvider>
      </ReportsQueryClientProvider>
    </Providers>
  );
}

