import AppLayout from '@/components/common/AppLayout';
import { Providers } from '@/components/common/Providers';
import { SelectedSchoolProvider } from '@/lib/context/SelectedSchoolContext';
import { ReportsQueryClientProvider } from '@/lib/reports/query-client';
import { getIsLtiUser } from '@/lib/server/me';

export default async function ProtectedShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // Decide the LTI (Schoology-embedded) shell server-side so it renders bare on
  // first paint — no flash of Settings/account chrome before a client check.
  const isLtiUser = await getIsLtiUser();

  return (
    <Providers>
      <ReportsQueryClientProvider>
        <SelectedSchoolProvider>
          <AppLayout isLtiUser={isLtiUser}>{children}</AppLayout>
        </SelectedSchoolProvider>
      </ReportsQueryClientProvider>
    </Providers>
  );
}

