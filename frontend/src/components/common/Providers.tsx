'use client';

import { GlobalProvider } from '@/lib/context/GlobalContext';
import type { AppMetadata, UserMetadata } from '@/lib/types/auth.types';

export function Providers({
  children,
  initialAuth,
}: {
  children: React.ReactNode;
  initialAuth?: {
    user: {
      id: string;
      email: string | null;
      created_at: string;
      user_metadata?: UserMetadata;
      app_metadata?: AppMetadata;
    } | null;
    mfaRequired?: boolean;
  };
}) {
  return <GlobalProvider initialAuth={initialAuth}>{children}</GlobalProvider>;
}

