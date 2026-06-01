'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import type { AccessibleSchool } from '@/lib/reports/types';

const STORAGE_KEY = 'gains.selectedSchoolId';

type SelectedSchoolContextValue = {
  /** The school_id currently scoping report requests, or null to use the
   *  backend's fallback (the user's primary school). */
  schoolId: string | null;
  setSchoolId: (schoolId: string | null) => void;
  schools: AccessibleSchool[];
  isLoading: boolean;
};

const SelectedSchoolContext = createContext<SelectedSchoolContextValue | null>(
  null,
);

function readPersisted(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function SelectedSchoolProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const { data, isLoading } = useQuery({
    queryKey: reportsKeys.schools(),
    queryFn: () => reportsApi.accessibleSchools(),
  });

  const schools = useMemo(() => data ?? [], [data]);

  const [schoolId, setSchoolIdState] = useState<string | null>(() =>
    readPersisted(),
  );

  const setSchoolId = useCallback((next: string | null) => {
    setSchoolIdState(next);
    if (typeof window === 'undefined') return;
    try {
      if (next) window.localStorage.setItem(STORAGE_KEY, next);
      else window.localStorage.removeItem(STORAGE_KEY);
    } catch {
      // Ignore storage failures (private mode, quota, etc.).
    }
  }, []);

  // Reconcile the selection once the accessible-schools list resolves:
  //   - single school accessible → always pin to it
  //   - persisted value no longer accessible → drop it (back to fallback)
  useEffect(() => {
    if (isLoading || schools.length === 0) return;

    if (schools.length === 1) {
      const only = schools[0].school_id;
      if (schoolId !== only) setSchoolId(only);
      return;
    }

    if (schoolId && !schools.some((s) => s.school_id === schoolId)) {
      setSchoolId(null);
    }
  }, [isLoading, schools, schoolId, setSchoolId]);

  const value = useMemo<SelectedSchoolContextValue>(
    () => ({ schoolId, setSchoolId, schools, isLoading }),
    [schoolId, setSchoolId, schools, isLoading],
  );

  return (
    <SelectedSchoolContext.Provider value={value}>
      {children}
    </SelectedSchoolContext.Provider>
  );
}

export function useSelectedSchool(): SelectedSchoolContextValue {
  const ctx = useContext(SelectedSchoolContext);
  if (!ctx) {
    throw new Error(
      'useSelectedSchool must be used within SelectedSchoolProvider',
    );
  }
  return ctx;
}
