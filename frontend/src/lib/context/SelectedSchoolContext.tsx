'use client';

import React, {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
} from 'react';
import { usePathname, useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import type { AccessibleSchool } from '@/lib/reports/types';

const STORAGE_KEY = 'gains.selectedSchoolId';

type SelectedSchoolContextValue = {
  /** The school_id currently scoping every report/dashboard request. Resolves
   *  to a concrete accessible school (never null) once the accessible-schools
   *  list has loaded, so assessment data can always be fetched. */
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

function persist(id: string | null) {
  if (typeof window === 'undefined') return;
  try {
    if (id) window.localStorage.setItem(STORAGE_KEY, id);
    else window.localStorage.removeItem(STORAGE_KEY);
  } catch {
    // Ignore storage failures (private mode, quota, etc.).
  }
}

export function SelectedSchoolProvider({
  children,
}: {
  children: React.ReactNode;
}) {
  const router = useRouter();
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const urlSchoolId = searchParams.get('school_id');

  const { data, isLoading } = useQuery({
    queryKey: reportsKeys.schools(),
    queryFn: () => reportsApi.accessibleSchools(),
  });

  const schools = useMemo(() => data ?? [], [data]);

  // The user's current choice. Seeded from the URL (a shared link) and then the
  // last-used school in this browser. Persists across in-app navigation because
  // this provider is mounted once at the /app layout.
  const [selected, setSelected] = useState<string | null>(
    () => urlSchoolId ?? readPersisted(),
  );

  const isAccessible = useCallback(
    (id: string | null | undefined): id is string =>
      !!id && schools.some((s) => s.school_id === id),
    [schools],
  );

  const setSchoolId = useCallback((next: string | null) => {
    // The URL + localStorage are reconciled by the sync effect below, so the
    // switcher only has to record the intent.
    setSelected(next);
  }, []);

  // 1) Adopt a school_id that arrives via the URL — a shared report link, or a
  //    browser back/forward — so the recipient's view scopes to the link's
  //    school rather than this browser's last selection.
  useEffect(() => {
    if (urlSchoolId && urlSchoolId !== selected) {
      setSelected(urlSchoolId);
    }
    // Intentionally keyed on urlSchoolId only: adopt external URL changes.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [urlSchoolId]);

  // 2) Once the accessible-schools list resolves, guarantee a CONCRETE school is
  //    selected (the first accessible one) when the current choice is missing or
  //    not accessible to this user. This is the "always pick a school by
  //    default" behaviour and prevents the no-school state that left assessment
  //    requests unscoped.
  useEffect(() => {
    if (isLoading || schools.length === 0) return;
    if (!isAccessible(selected)) {
      setSelected(schools[0].school_id);
    }
  }, [isLoading, schools, selected, isAccessible]);

  // 3) Mirror the resolved school into the URL (so the link is shareable) and
  //    localStorage (so it persists). Only writes when the URL is missing or
  //    out of sync, which makes it idempotent and loop-free.
  useEffect(() => {
    if (!isAccessible(selected)) return;
    persist(selected);
    if (urlSchoolId !== selected) {
      const sp = new URLSearchParams(searchParams.toString());
      sp.set('school_id', selected);
      router.replace(`${pathname}?${sp.toString()}`, { scroll: false });
    }
  }, [selected, urlSchoolId, isAccessible, pathname, searchParams, router]);

  // Exposed school: the valid selection, or a best-effort hint while the
  // accessible-schools list is still loading (so a shared link fetches the
  // right school on first paint), or the first accessible school as the floor.
  const schoolId = useMemo<string | null>(() => {
    if (isAccessible(selected)) return selected;
    if (isLoading || schools.length === 0) return urlSchoolId ?? selected ?? null;
    return schools[0]?.school_id ?? null;
  }, [selected, isAccessible, isLoading, schools, urlSchoolId]);

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
