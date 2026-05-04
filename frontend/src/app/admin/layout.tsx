import { redirect } from 'next/navigation';
import { Providers } from '@/components/common/Providers';
import AdminLayout from '@/components/admin/AdminLayout';
import { AdminClaimsProvider } from '@/components/admin/AdminClaimsContext';
import AccessDenied from '@/components/common/AccessDenied';
import { canSeeAdminEntry } from '@/lib/rbac/access';
import { getMe, getUserClaims } from '@/lib/server/me';

export const dynamic = 'force-dynamic';

export default async function Layout({ children }: { children: React.ReactNode }) {
  const user = await getMe();

  if (!user) {
    redirect('/auth/login?returnTo=/admin');
  }

  const claims = getUserClaims(user);

  if (!canSeeAdminEntry(claims)) {
    return (
      <Providers>
        <AccessDenied
          message="You do not have permission to access the admin area."
          returnTo="/app"
          returnLabel="Back to App"
        />
      </Providers>
    );
  }

  return (
    <Providers
      initialAuth={{
        user: {
          id: user.id,
          email: user.email,
          created_at: user.created_at || new Date().toISOString(),
          user_metadata: user.user_metadata,
          app_metadata: user.app_metadata,
        },
        mfaRequired: user.requiresMFA,
      }}
    >
      <AdminClaimsProvider claims={claims}>
        <AdminLayout>{children}</AdminLayout>
      </AdminClaimsProvider>
    </Providers>
  );
}

