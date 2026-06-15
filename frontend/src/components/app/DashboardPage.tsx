'use client';

import Link from 'next/link';
import { useCallback, useEffect, useRef, useState } from 'react';
import { useInfiniteQuery, useQuery } from '@tanstack/react-query';
import {
  ArrowUpRight,
  BookOpen,
  GraduationCap,
  ListChecks,
  Percent,
  Users,
} from 'lucide-react';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import { getReportsByGroup } from '@/lib/reports/report-types';
import type { AssessmentFilters } from '@/lib/reports/types';
import { StatCard } from '@/components/app/StatCard';
import { Button } from '@/components/ui/button';
import DashboardHeader from '@/components/app/dashboard/DashboardHeader';
import DashboardFilters from '@/components/app/dashboard/DashboardFilters';
import AssessmentsSummaryTable, {
  type AssessmentSortKey,
} from '@/components/app/dashboard/AssessmentsSummaryTable';

const PROGRAM_REPORTS = getReportsByGroup('program');
const PAGE_SIZE = 25;

/** First-click direction per assessment sort column (mirrors useTableSort). */
const INITIAL_DIR: Record<AssessmentSortKey, 'asc' | 'desc'> = {
  date: 'desc',
  item: 'asc',
  grade: 'asc',
  students: 'desc',
  average: 'desc',
};

/** Latest academic year = highest session string (e.g. "2025-26" > "2024-25"). */
function latestSession(sessions: { session: string | null }[]): string | undefined {
  return sessions
    .map((s) => s.session)
    .filter((s): s is string => !!s)
    .sort((a, b) => b.localeCompare(a))[0];
}

export function DashboardPage() {
  const { schoolId } = useSelectedSchool();
  const [filters, setFilters] = useState<AssessmentFilters>({});
  const [search, setSearch] = useState('');
  const [debouncedSearch, setDebouncedSearch] = useState('');
  const [sort, setSort] = useState<AssessmentSortKey>('date');
  const [dir, setDir] = useState<'asc' | 'desc'>('desc');
  const [inited, setInited] = useState(false);
  const initedSchool = useRef<string | null>(null);

  // Debounce the search before it hits the server query key, so each keystroke
  // doesn't fire a request. The live `search` still drives the client-side
  // By-Standard / By-Strand filters instantly.
  useEffect(() => {
    const t = setTimeout(() => setDebouncedSearch(search.trim()), 300);
    return () => clearTimeout(t);
  }, [search]);

  const onSort = useCallback(
    (col: AssessmentSortKey) => {
      if (col === sort) {
        setDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      } else {
        setSort(col);
        setDir(INITIAL_DIR[col]);
      }
    },
    [sort],
  );

  // Sessions feed the default-year pick. Same query key as ReportFilters', so
  // react-query serves one shared request (no duplicate call).
  const sessionsQ = useQuery({
    queryKey: reportsKeys.sessions(schoolId ?? undefined),
    queryFn: () => reportsApi.sessions(schoolId ?? undefined),
  });

  // Default the scope to the latest academic year, once per school. Resets
  // filters/search/sort on a school switch so each school opens on its newest
  // year, newest-first, at page 0.
  useEffect(() => {
    const list = sessionsQ.data;
    if (!list) return;
    const sid = schoolId ?? null;
    if (initedSchool.current === sid && inited) return;
    initedSchool.current = sid;
    const latest = latestSession(list);
    setFilters(latest ? { session: latest } : {});
    setSearch('');
    setDebouncedSearch('');
    setSort('date');
    setDir('desc');
    setInited(true);
  }, [sessionsQ.data, schoolId, inited]);

  const summaryFilters = { ...filters, school_id: schoolId ?? undefined };

  // standard-summary is the single source for the header (school name/logo/
  // session), the KPI strip, the school-wide grade-average marker AND the
  // "By Standard" table variant (bounded — fetched whole).
  const stdQ = useQuery({
    queryKey: reportsKeys.standardSummary(summaryFilters),
    queryFn: () => reportsApi.standardSummary(summaryFilters),
    enabled: inited,
  });
  const strandQ = useQuery({
    queryKey: reportsKeys.strandSummary(summaryFilters),
    queryFn: () => reportsApi.strandSummary(summaryFilters),
    enabled: inited,
  });

  // Assessments are unbounded → true server-side pagination. The query lives
  // here (not inside the table) so the "Assessments" KPI total survives variant
  // switches and the table just renders the accumulated pages.
  const asmtQ = useInfiniteQuery({
    queryKey: reportsKeys.assessmentSummaries(filters, schoolId ?? undefined, {
      q: debouncedSearch,
      sort,
      dir,
    }),
    queryFn: ({ pageParam }) =>
      reportsApi.assessmentSummaries(filters, schoolId ?? undefined, {
        q: debouncedSearch || undefined,
        sort,
        dir,
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    enabled: inited,
    initialPageParam: 0,
    getNextPageParam: (lastPage, allPages, lastPageParam) => {
      const loaded = allPages.reduce((n, p) => n + p.rows.length, 0);
      return loaded >= lastPage.total ? undefined : lastPageParam + PAGE_SIZE;
    },
    placeholderData: (prev) => prev,
  });

  const kpis = stdQ.data?.kpis;
  const school = stdQ.data?.school;
  const schoolAverage = kpis?.grade_average ?? null;
  const assessmentRows = asmtQ.data?.pages.flatMap((p) => p.rows) ?? [];
  const assessmentTotal = asmtQ.data?.pages[0]?.total ?? 0;
  const headerLoading = !inited || stdQ.isLoading;
  const asmtLoading = !inited || asmtQ.isPending;

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <DashboardHeader
        schoolName={school?.name ?? null}
        logoUrl={school?.logo_url ?? null}
        currentSession={school?.current_session ?? null}
        loading={headerLoading}
      />

      <DashboardFilters
        filters={filters}
        onFiltersChange={setFilters}
        search={search}
        onSearchChange={setSearch}
      />

      {/* School-scoped KPI strip (legacy KPI cardVisuals) */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Total Students" value={kpis?.total_students ?? '—'} icon={Users} loading={headerLoading} />
        <StatCard label="Total Standards" value={kpis?.total_standards ?? '—'} icon={GraduationCap} loading={headerLoading} />
        <StatCard label="Total Questions" value={kpis?.total_questions ?? '—'} icon={ListChecks} loading={headerLoading} />
        <StatCard label="Assessments" value={asmtLoading ? '—' : assessmentTotal} icon={BookOpen} loading={asmtLoading} />
        <StatCard label="Grade Average" value={kpis?.grade_average_pct ?? '—'} icon={Percent} loading={headerLoading} />
      </div>

      <AssessmentsSummaryTable
        schoolAverage={schoolAverage}
        assessments={assessmentRows}
        assessmentTotal={assessmentTotal}
        assessmentHasMore={asmtQ.hasNextPage}
        assessmentFetchingMore={asmtQ.isFetchingNextPage}
        onAssessmentFetchMore={() => void asmtQ.fetchNextPage()}
        assessmentSort={sort}
        assessmentDir={dir}
        onAssessmentSort={onSort}
        assessmentLoading={asmtLoading}
        standards={stdQ.data?.standards ?? []}
        strands={strandQ.data?.strands_rollup ?? []}
        search={search}
        loading={!inited || stdQ.isLoading || strandQ.isLoading}
      />

      {/* Program (school-wide) reports — always-visible launcher buttons,
          the modern homage to the legacy rounded-pill report navigator. */}
      <section className="space-y-2 pt-1">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Program reports
        </p>
        <nav aria-label="Program reports" className="flex flex-wrap gap-2">
          {PROGRAM_REPORTS.map((r) => {
            const Icon = r.icon;
            return (
              <Button
                key={r.slug}
                asChild
                variant="outline"
                className="group h-11 flex-1 justify-start gap-2 sm:flex-none"
              >
                <Link href={`/app/reports/${r.slug}`} aria-label={`Open ${r.canonicalName}`}>
                  <Icon className="h-4 w-4 text-primary" />
                  <span className="text-sm font-medium">{r.shortName}</span>
                  <ArrowUpRight className="ml-auto h-3.5 w-3.5 text-muted-foreground/60 transition-colors group-hover:text-primary sm:ml-2" />
                </Link>
              </Button>
            );
          })}
        </nav>
      </section>
    </div>
  );
}
