'use client';

import React, { createContext, useContext } from 'react';
import type { UserClaims } from '@/lib/rbac/access';

type AdminClaimsContextValue = {
  claims: UserClaims;
};

const AdminClaimsContext = createContext<AdminClaimsContextValue | null>(null);

export function AdminClaimsProvider({
  claims,
  children,
}: {
  claims: UserClaims;
  children: React.ReactNode;
}) {
  return (
    <AdminClaimsContext.Provider value={{ claims }}>
      {children}
    </AdminClaimsContext.Provider>
  );
}

export function useAdminClaims(): UserClaims {
  const ctx = useContext(AdminClaimsContext);
  if (!ctx) {
    throw new Error('useAdminClaims must be used within AdminClaimsProvider');
  }
  return ctx.claims;
}

