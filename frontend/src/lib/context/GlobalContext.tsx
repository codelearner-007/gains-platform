'use client';

import React, { createContext, useCallback, useContext, useEffect, useRef, useState } from 'react';
import { authService } from '@/lib/services/auth.service';
import type { AppMetadata, UserMetadata } from '@/lib/types/auth.types';
import { setAnalyticsUserId } from '@/lib/analytics/ga';

type User = {
  email: string;
  id: string;
  registered_at: Date;
  user_metadata?: UserMetadata;
  app_metadata?: AppMetadata;
};

interface GlobalContextType {
  loading: boolean;
  user: User | null;
  mfaRequired: boolean;
  isFullyAuthenticated: boolean;
  clearUser: () => void;
  refreshUser: () => Promise<void>;
  /**
   * Used by server layouts to pre-hydrate auth state and skip the initial client fetch.
   */
  setAuthFromLogin: (payload: {
    user: {
      id: string;
      email: string | null;
      created_at?: string;
      user_metadata?: UserMetadata;
      app_metadata?: AppMetadata;
    } | null;
    mfaRequired?: boolean;
  }) => void;
}

const GlobalContext = createContext<GlobalContextType | undefined>(undefined);

export function GlobalProvider({
  children,
  initialAuth,
}: {
  children: React.ReactNode;
  initialAuth?: {
    user: {
      id: string;
      email: string | null;
      created_at?: string;
      user_metadata?: UserMetadata;
      app_metadata?: AppMetadata;
    } | null;
    mfaRequired?: boolean;
  };
}) {
  const [loading, setLoading] = useState(!initialAuth);
  const [user, setUser] = useState<User | null>(null);
  const [mfaRequired, setMfaRequired] = useState(!!initialAuth?.mfaRequired);
  const [mounted, setMounted] = useState(false);
  const didInitialLoadRef = useRef(false);

  const clearUser = useCallback(() => {
    setUser(null);
    setMfaRequired(false);
    setLoading(false);
  }, []);

  const setAuthFromLogin: GlobalContextType['setAuthFromLogin'] = useCallback((payload) => {
    if (!payload.user) {
      clearUser();
      return;
    }

    setUser({
      email: payload.user.email ?? '',
      id: payload.user.id,
      registered_at: payload.user.created_at ? new Date(payload.user.created_at) : new Date(),
      user_metadata: payload.user.user_metadata,
      app_metadata: payload.user.app_metadata,
    });

    setMfaRequired(!!payload.mfaRequired);
    setLoading(false);
  }, [clearUser]);

  // Pre-hydrate from server (admin/app layouts) to avoid first-mount refetch.
  useEffect(() => {
    if (!initialAuth) return;
    setAuthFromLogin({ user: initialAuth.user, mfaRequired: initialAuth.mfaRequired });
    didInitialLoadRef.current = true;
  }, [initialAuth, setAuthFromLogin]);

  const loadUser = useCallback(async () => {
    setLoading(true);
    try {
      const { user: userData, requiresMFA } = await authService.getCurrentUser();

      if (userData) {
        setUser({
          email: userData.email ?? '',
          id: userData.id,
          registered_at: userData.created_at ? new Date(userData.created_at) : new Date(),
          user_metadata: userData.user_metadata,
          app_metadata: userData.app_metadata,
        });
        setMfaRequired(!!requiresMFA);
      } else {
        setUser(null);
        setMfaRequired(false);
      }
    } catch (error) {
      console.error('Error loading user data:', error);
      setUser(null);
      setMfaRequired(false);
    } finally {
      setLoading(false);
    }
  }, []);

  const refreshUser = loadUser;

  // Mounted check to prevent hydration mismatch
  useEffect(() => {
    setMounted(true);
  }, []);

  useEffect(() => {
    // Only run on client after mount to prevent hydration issues
    if (!mounted) return;

    // Prevent duplicate calls in React Strict Mode for the initial load.
    if (didInitialLoadRef.current) return;
    didInitialLoadRef.current = true;

    loadUser();
  }, [mounted, loadUser]);

  useEffect(() => {
    setAnalyticsUserId(user?.id ?? null);
  }, [user?.id]);

  const isFullyAuthenticated = !!user && !mfaRequired;

  return (
    <GlobalContext.Provider
      value={{
        loading,
        user,
        mfaRequired,
        isFullyAuthenticated,
        clearUser,
        refreshUser,
        setAuthFromLogin,
      }}
    >
      {children}
    </GlobalContext.Provider>
  );
}

export function useGlobal(): GlobalContextType {
  const context = useContext(GlobalContext);
  if (context === undefined) {
    throw new Error('useGlobal must be used within a GlobalProvider');
  }
  return context;
}
