import type React from 'react';
import { notFound, redirect } from 'next/navigation';
import AdminRBACPage from '@/components/admin/modules/rbac/AdminRBACPage';
import AdminUsersPage from '@/components/admin/modules/users/AdminUsersPage';
import AdminAuditPage from '@/components/admin/modules/audit/AdminAuditPage';
import { canAccessAdminModule } from '@/lib/rbac/access';
import { getMe, getUserClaims } from '@/lib/server/me';
import AccessDenied from '@/components/common/AccessDenied';

export const dynamic = 'force-dynamic';

const MODULE_COMPONENTS: Record<string, React.ComponentType> = {
  rbac: AdminRBACPage,
  users: AdminUsersPage,
  audit: AdminAuditPage,
};

export default async function AdminModulePage({
  params,
}: {
  params: Promise<{ module: string }>;
}) {
  const { module } = await params;
  const Component = MODULE_COMPONENTS[module];

  if (!Component) {
    notFound();
  }

  const user = await getMe();
  if (!user) {
    redirect('/auth/login?returnTo=/admin');
  }

  const claims = getUserClaims(user);
  if (!canAccessAdminModule(claims, module)) {
    return (
      <AccessDenied
        message={`You do not have permission to access the ${module} module.`}
        returnTo="/admin"
        returnLabel="Back to Admin"
      />
    );
  }

  return <Component />;
}
