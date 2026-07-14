'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  keepPreviousData,
  useInfiniteQuery,
  useIsFetching,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { AlertCircle, ArrowUpRight } from 'lucide-react';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import { getReportsByGroup } from '@/lib/reports/report-types';
import type { AssessmentFilters } from '@/lib/reports/types';
import { useDebounce } from '@/hooks/useDebounce';
import { Button } from '@/components/ui/button';
import DashboardHeader from '@/components/app/dashboard/DashboardHeader';
import SearchInput from '@/components/app/dashboard/SearchInput';
import FilterPopover from '@/components/app/dashboard/FilterPopover';
import KpiHeroBand from '@/components/app/dashboard/KpiHeroBand';
import SubjectKpiCards from '@/components/app/dashboard/SubjectKpiCards';
import GradeChips from '@/components/app/dashboard/GradeChips';
import AssessmentsSummaryTable, {
  type AssessmentSortKey,
  type StrandRowSortKey,
} from '@/components/app/dashboard/AssessmentsSummaryTable';
import StudentsSummaryTable, {
  type StudentSortKey,
} from '@/components/app/dashboard/StudentsSummaryTable';

const PROGRAM_REPORTS = getReportsByGroup('program');
const PAGE_SIZE = 25;

/** Shared getNextPageParam for the server-paginated grids: stop once every
 *  filter-scoped row is loaded, else advance by one page. */
function nextPageParam(
  lastPage: { rows: unknown[]; total: number },
  allPages: { rows: unknown[] }[],
  lastPageParam: number,
): number | undefined {
  const loaded = allPages.reduce((n, p) => n + p.rows.length, 0);
  return loaded >= lastPage.total ? undefined : lastPageParam + PAGE_SIZE;
}

/** First-click direction per By-Assessment sort column (mirrors useTableSort). */
const ASMT_INITIAL_DIR: Record<AssessmentSortKey, 'asc' | 'desc'> = {
  date: 'desc',
  item: 'asc',
  grade: 'asc',
  students: 'desc',
  average: 'desc',
};

/** First-click direction per By-Strand sort column. */
const STRAND_INITIAL_DIR: Record<StrandRowSortKey, 'asc' | 'desc'> = {
  date: 'desc',
  strand: 'asc',
  grade: 'asc',
  standards: 'desc',
  questions: 'desc',
  average: 'desc',
};

/** First-click direction per By-Students sort column. */
const STUDENT_INITIAL_DIR: Record<StudentSortKey, 'asc' | 'desc'> = {
  name: 'asc',
  overall: 'desc',
  assessments: 'desc',
  subjects: 'desc',
};

/** The single dashboard view selector — four lenses on the same scoped data.
 *  Merges the old top "By Assessment / By Student" mode with the panel's
 *  "By Assessment / By Standard / By Strand" grouping into one control, so
 *  "Assessment" no longer means two different things. */
type DashView = 'assessment' | 'student' | 'standard' | 'strand';
const VIEW_OPTIONS: { value: DashView; label: string }[] = [
  { value: 'assessment', label: 'Assessments' },
  { value: 'student', label: 'Students' },
  { value: 'standard', label: 'Standards' },
  { value: 'strand', label: 'Strands' },
];

/** Latest academic year = highest session string (e.g. "2025-26" > "2024-25"). */
function latestSession(sessions: { session: string | null }[]): string | undefined {
  return sessions
    .map((s) => s.session)
    .filter((s): s is string => !!s)
    .sort((a, b) => b.localeCompare(a))[0];
}

export function DashboardPage() {
  const { schoolId, isLoading: schoolLoading } = useSelectedSchool();
  const queryClient = useQueryClient();
  const [filters, setFilters] = useState<AssessmentFilters>({});
  const [search, setSearch] = useState('');
  const debouncedSearch = useDebounce(search.trim(), 300);
  const [sort, setSort] = useState<AssessmentSortKey>('date');
  const [dir, setDir] = useState<'asc' | 'desc'>('desc');
  const [strandSort, setStrandSort] = useState<StrandRowSortKey>('date');
  const [strandDir, setStrandDir] = useState<'asc' | 'desc'>('desc');
  const [view, setView] = useState<DashView>('assessment');
  const [studentSort, setStudentSort] = useState<StudentSortKey>('name');
  const [studentDir, setStudentDir] = useState<'asc' | 'desc'>('asc');
  const [inited, setInited] = useState(false);
  // Gate the subject-scoped queries until the first-subject default has been
  // applied, so each fires exactly ONCE with the final {session, grade, subject}
  // instead of 2–3× as the staged defaults land.
  const [defaultsReady, setDefaultsReady] = useState(false);
  const [refreshing, setRefreshing] = useState(false);
  const initedSchool = useRef<string | null>(null);
  // Default-select runs once per school: first available grade, then the first
  // subject for that grade. Refs (not state) so it never re-applies after the
  // user deselects.
  const autoDefault = useRef({ grade: false, subject: false });

  const onSort = useCallback(
    (col: AssessmentSortKey) => {
      if (col === sort) setDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      else {
        setSort(col);
        setDir(ASMT_INITIAL_DIR[col]);
      }
    },
    [sort],
  );

  const onStrandSort = useCallback(
    (col: StrandRowSortKey) => {
      if (col === strandSort) setStrandDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      else {
        setStrandSort(col);
        setStrandDir(STRAND_INITIAL_DIR[col]);
      }
    },
    [strandSort],
  );

  const onStudentSort = useCallback(
    (col: StudentSortKey) => {
      if (col === studentSort) setStudentDir((d) => (d === 'asc' ? 'desc' : 'asc'));
      else {
        setStudentSort(col);
        setStudentDir(STUDENT_INITIAL_DIR[col]);
      }
    },
    [studentSort],
  );

  // Sessions feed the default-year pick. Shared query key with ReportFilters /
  // FilterPopover, so react-query serves one request.
  const sessionsQ = useQuery({
    queryKey: reportsKeys.sessions(schoolId ?? undefined),
    queryFn: () => reportsApi.sessions(schoolId ?? undefined),
    staleTime: 5 * 60_000, // dims change only on a pipeline refresh
  });

  // Grades feed the front grade chips.
  const gradesQ = useQuery({
    queryKey: reportsKeys.grades(schoolId ?? undefined),
    queryFn: () => reportsApi.grades(schoolId ?? undefined),
    staleTime: 5 * 60_000,
  });

  // Default the scope to the latest academic year, once per school; reset all
  // filter/search/sort state on a school switch.
  useEffect(() => {
    // Wait for the selected school to settle. effectiveSchoolId is null while
    // the accessible-schools list loads, then resolves to the real id with no
    // user action — running before that would init on the null id and then
    // re-reset (clobbering early user state + double-fetching) once it lands.
    if (schoolLoading) return;
    // Wait for BOTH cheap dims (they load in parallel) so we can apply the
    // year + first-grade default in ONE setFilters — the subject-scoped queries
    // then fire once with {session, grade} instead of once per staged default.
    if (!sessionsQ.data || !gradesQ.data) return;
    const sid = schoolId ?? null;
    if (initedSchool.current === sid && inited) return;
    initedSchool.current = sid;
    autoDefault.current = { grade: true, subject: false };
    setDefaultsReady(false);
    const latest = latestSession(sessionsQ.data);
    const firstGrade = Array.from(
      new Set(
        (gradesQ.data ?? [])
          .map((g) => g.grade)
          .filter((g): g is string => !!g),
      ),
    )[0];
    setFilters({
      ...(latest ? { session: latest } : {}),
      ...(firstGrade ? { grade: firstGrade } : {}),
    });
    setSearch('');
    setSort('date');
    setDir('desc');
    setStrandSort('date');
    setStrandDir('desc');
    setView('assessment');
    setStudentSort('name');
    setStudentDir('asc');
    setInited(true);
  }, [sessionsQ.data, gradesQ.data, schoolId, inited, schoolLoading]);

  const summaryFilters = { ...filters, school_id: schoolId ?? undefined };
  // Subject cards + their %s scope by year/type/grade, NOT by the selected
  // subject (so every card stays visible to switch between).
  const overviewFilters = {
    session: filters.session,
    category: filters.category,
    grade: filters.grade,
    school_id: schoolId ?? undefined,
  };

  // Subject cards + dataset-refresh timestamp.
  const overviewQ = useQuery({
    queryKey: reportsKeys.dashboardOverview(overviewFilters),
    queryFn: () => reportsApi.dashboardOverview(overviewFilters),
    enabled: inited,
    placeholderData: keepPreviousData,
  });

  // standard-summary: header (name/logo/session) + KPI strip + school-wide
  // grade-average marker + the bounded "By Standard" table variant.
  const stdQ = useQuery({
    queryKey: reportsKeys.standardSummary(summaryFilters),
    queryFn: () => reportsApi.standardSummary(summaryFilters),
    enabled: inited && defaultsReady,
    placeholderData: keepPreviousData,
  });

  // By Assessment — server-paginated (unbounded set).
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
    enabled: inited && defaultsReady,
    initialPageParam: 0,
    getNextPageParam: nextPageParam,
    placeholderData: (prev) => prev,
  });

  // By Strand — server-paginated legacy per-(assessment × strand) grid.
  const strandRowsQ = useInfiniteQuery({
    queryKey: reportsKeys.strandRows(filters, schoolId ?? undefined, {
      q: debouncedSearch,
      sort: strandSort,
      dir: strandDir,
    }),
    queryFn: ({ pageParam }) =>
      reportsApi.strandRows(filters, schoolId ?? undefined, {
        q: debouncedSearch || undefined,
        sort: strandSort,
        dir: strandDir,
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    // Strand grid renders only inside the Strands view — defer it off first paint.
    enabled: inited && defaultsReady && view === 'strand',
    initialPageParam: 0,
    getNextPageParam: nextPageParam,
    placeholderData: (prev) => prev,
  });

  // By Students — server-paginated roster (same filter scope; only fetched
  // while the Students view is active).
  const studentsQ = useInfiniteQuery({
    queryKey: reportsKeys.studentsBrowse(filters, schoolId ?? undefined, {
      q: debouncedSearch,
      sort: studentSort,
      dir: studentDir,
    }),
    queryFn: ({ pageParam }) =>
      reportsApi.studentsBrowse(filters, schoolId ?? undefined, {
        q: debouncedSearch || undefined,
        sort: studentSort,
        dir: studentDir,
        limit: PAGE_SIZE,
        offset: pageParam,
      }),
    enabled: inited && defaultsReady && view === 'student',
    initialPageParam: 0,
    getNextPageParam: nextPageParam,
    placeholderData: (prev) => prev,
  });

  const handleRefresh = useCallback(async () => {
    setRefreshing(true);
    try {
      await queryClient.invalidateQueries({ queryKey: reportsKeys.all });
    } finally {
      setRefreshing(false);
    }
  }, [queryClient]);

  const kpis = stdQ.data?.kpis;
  const school = stdQ.data?.school;
  const schoolAverage = kpis?.grade_average ?? null;
  const subjects = useMemo(() => overviewQ.data?.subjects ?? [], [overviewQ.data]);
  const refreshedAt = overviewQ.data?.refreshed_at ?? null;
  const grades = useMemo(
    () =>
      Array.from(
        new Set(
          (gradesQ.data ?? [])
            .map((g) => g.grade)
            .filter((g): g is string => !!g),
        ),
      ),
    [gradesQ.data],
  );

  // Subject default (once per school): after the grade-scoped subject cards
  // load, pick the first subject for the grade so a concrete card is highlighted
  // — the subject must come from the grade-scoped list. Grade + year were
  // already defaulted in the init effect. `defaultsReady` flips true on EVERY
  // exit path (subject picked, no subjects, or overview error) so the
  // subject-scoped queries never deadlock; ref-gated so it never fights a
  // user deselect.
  useEffect(() => {
    if (!inited || autoDefault.current.subject) return;
    if (overviewQ.isError) {
      autoDefault.current.subject = true;
      setDefaultsReady(true);
      return;
    }
    if (!overviewQ.data || overviewQ.isFetching) return;
    autoDefault.current.subject = true;
    const subs = overviewQ.data.subjects;
    if (subs.length > 0) {
      setFilters((f) => (f.subject ? f : { ...f, subject: subs[0].subject }));
    }
    setDefaultsReady(true);
  }, [inited, overviewQ.data, overviewQ.isFetching, overviewQ.isError]);

  const assessmentRows = useMemo(
    () => asmtQ.data?.pages.flatMap((p) => p.rows) ?? [],
    [asmtQ.data],
  );
  const assessmentTotal = asmtQ.data?.pages[0]?.total ?? 0;
  // Chronological per-assessment grade averages for the hero sparkline (from the
  // already-loaded rows — no extra request).
  const gradeTrend = useMemo(
    () =>
      assessmentRows
        .filter((r) => typeof r.grade_average === 'number' && r.assessment_date)
        .slice()
        .sort((a, b) =>
          (a.assessment_date ?? '') < (b.assessment_date ?? '') ? -1 : 1,
        )
        .map((r) => r.grade_average as number),
    [assessmentRows],
  );
  const strandRows = useMemo(
    () => strandRowsQ.data?.pages.flatMap((p) => p.rows) ?? [],
    [strandRowsQ.data],
  );
  const strandTotal = strandRowsQ.data?.pages[0]?.total ?? 0;
  const studentRows = useMemo(
    () => studentsQ.data?.pages.flatMap((p) => p.rows) ?? [],
    [studentsQ.data],
  );
  const studentTotal = studentsQ.data?.pages[0]?.total ?? 0;
  const studentFetching = studentsQ.isFetching && !studentsQ.isFetchingNextPage;
  const studentLoading = view === 'student' && (!inited || studentsQ.isPending);

  const headerLoading = !inited || stdQ.isLoading;
  // In-flight (refetch) state — NOT a scroll fetch-more — for the two grids.
  const asmtFetching = asmtQ.isFetching && !asmtQ.isFetchingNextPage;
  const strandFetching = strandRowsQ.isFetching && !strandRowsQ.isFetchingNextPage;
  const asmtLoading = !inited || asmtQ.isPending;
  const strandLoading = view === 'strand' && (!inited || strandRowsQ.isPending);
  const subjectsLoading = !inited || overviewQ.isLoading;
  // Search spinner: while the debounce is settling OR the server query for the
  // (debounced) term is in flight — but ONLY when a search term is active, so
  // subject/grade/year filtering doesn't trip it (which would swap the search
  // field's clear-X for a spinner mid-use).
  const searchLoading =
    search.trim() !== debouncedSearch ||
    (debouncedSearch.length > 0 &&
      (view === 'student' ? studentFetching : asmtFetching || strandFetching));

  const anyError =
    overviewQ.isError ||
    stdQ.isError ||
    asmtQ.isError ||
    strandRowsQ.isError ||
    studentsQ.isError;

  // "Data is streaming in" — ANY filter-dependent query refetching. Drives the
  // subtle dim of the CONTENT while a filter change loads; it does NOT lock the
  // filter controls (selection is client state and flips instantly, and
  // keepPreviousData makes stale-response interleaving safe — last click wins).
  const dataStreaming =
    overviewQ.isFetching ||
    stdQ.isFetching ||
    asmtFetching ||
    strandFetching ||
    studentFetching;

  // Single "something is loading" signal for the top progress bar.
  const anyFetching = useIsFetching({ queryKey: reportsKeys.all }) > 0;

  // KPIs are computed at the per-question OVERALL grain (no section), so they
  // stay school-wide; flag that only when a section narrows the tables.
  const schoolWideHint = filters.section ? 'school-wide' : undefined;

  return (
    <div className="relative isolate mx-auto max-w-7xl space-y-6">
      {/* Subtle brand wash behind the header — ambient warmth, not chrome. */}
      <div
        aria-hidden
        className="bg-brand-glow pointer-events-none absolute inset-x-0 -top-6 -z-10 h-64"
      />
      {/* Single "data is streaming" signal — a thin brand bar; never blocks.
          suppressHydrationWarning: the class derives from client-only
          useIsFetching (0 during SSR), so a first-paint mismatch is expected. */}
      <div
        aria-hidden
        suppressHydrationWarning
        className={`pointer-events-none absolute inset-x-0 -top-1 z-20 h-0.5 origin-left rounded-full bg-primary transition-opacity duration-300 ${
          anyFetching ? 'animate-pulse opacity-90' : 'opacity-0'
        }`}
      />
      <DashboardHeader
        schoolName={school?.name ?? null}
        logoUrl={school?.logo_url ?? null}
        currentSession={school?.current_session ?? null}
        loading={headerLoading}
        actions={
          <FilterPopover
            filters={filters}
            onChange={setFilters}
            refreshedAt={refreshedAt}
            onRefresh={handleRefresh}
            refreshing={refreshing}
          />
        }
      />

      {anyError && (
        <div className="flex items-center justify-between gap-3 rounded-lg border border-destructive/30 bg-destructive/10 px-4 py-3 text-sm">
          <span className="flex items-center gap-2 text-destructive">
            <AlertCircle className="h-4 w-4 shrink-0" />
            Some dashboard data failed to load.
          </span>
          <Button variant="outline" size="sm" onClick={handleRefresh} disabled={refreshing}>
            Retry
          </Button>
        </div>
      )}

      {/* Subject — primary subject slicer (legacy). Perf colour lives on the %. */}
      <section className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground">Subject</p>
        <SubjectKpiCards
          subjects={subjects}
          selected={filters.subject}
          onSelect={(subject) => setFilters((f) => ({ ...f, subject }))}
          loading={subjectsLoading}
        />
      </section>

      {/* Grade — primary grade slicer (legacy). */}
      <section className="space-y-1.5">
        <p className="text-xs font-medium text-muted-foreground">Grade</p>
        <GradeChips
          grades={grades}
          selected={filters.grade}
          onSelect={(grade) =>
            // Changing the grade invalidates the grade-scoped selections, so clear
            // the subject + section-instructor (a stale subject would point at a
            // card that no longer exists; a stale grade×instructor combo goes
            // empty). Academic year + assessment type are grade-independent and
            // are intentionally preserved.
            setFilters((f) => ({ ...f, grade, subject: undefined, instructor: undefined }))
          }
          loading={!inited || gradesQ.isLoading}
        />
      </section>

      {/* KPI hero band (legacy KPI cardVisuals). Grade Average is the focal
          brand-gradient cell (with a year-trend sparkline); the four counts sit
          beside it. Total Students / Questions / Grade Average come from the
          per-question OVERALL cube, which — like legacy PowerBI — has no section
          grain, so they stay school-wide; marked "school-wide" when a section
          is active. */}
      <KpiHeroBand
        gradeAveragePct={kpis?.grade_average_pct ?? '—'}
        totalStudents={kpis?.total_students ?? '—'}
        totalStandards={kpis?.total_standards ?? '—'}
        totalQuestions={kpis?.total_questions ?? '—'}
        totalAssessments={assessmentTotal}
        trend={gradeTrend}
        loading={headerLoading}
        schoolWideHint={schoolWideHint}
      />

      {/* Summary — one 4-view selector (resolves the old double "By Assessment")
          + a row-scoped search, then the table panel. */}
      <section className="space-y-3">
        <div className="flex flex-wrap items-center gap-3">
          <h2 className="text-sm font-semibold text-foreground">Summary</h2>
          <div
            role="tablist"
            aria-label="Summary view"
            className="inline-flex items-center gap-0.5 rounded-lg bg-muted p-0.5"
          >
            {VIEW_OPTIONS.map((v) => {
              const active = view === v.value;
              return (
                <button
                  key={v.value}
                  role="tab"
                  aria-selected={active}
                  onClick={() => setView(v.value)}
                  className={[
                    'h-7 rounded-md px-3 text-xs font-medium transition-colors',
                    'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring',
                    active
                      ? 'bg-primary text-primary-foreground shadow-sm'
                      : 'text-muted-foreground hover:bg-background/70 hover:text-foreground',
                  ].join(' ')}
                >
                  {v.label}
                </button>
              );
            })}
          </div>
          <div className="ml-auto min-w-0 basis-full sm:basis-auto">
            <SearchInput
              value={search}
              onChange={setSearch}
              loading={searchLoading}
              resultCount={view === 'student' ? studentTotal : assessmentTotal}
            />
          </div>
        </div>

        {/* Content persists (keepPreviousData) and dims while a filter change
            streams in — never blanks to skeletons after first load. */}
        <div
          className={`transition-opacity duration-200 ${dataStreaming ? 'opacity-60' : ''}`}
        >
        {view === 'student' ? (
          <StudentsSummaryTable
            schoolId={schoolId ?? undefined}
            session={filters.session}
            classAverage={schoolAverage}
            rows={studentRows}
            total={studentTotal}
            hasMore={studentsQ.hasNextPage}
            isFetchingMore={studentsQ.isFetchingNextPage}
            onFetchMore={() => void studentsQ.fetchNextPage()}
            sort={studentSort}
            dir={studentDir}
            onSort={onStudentSort}
            loading={studentLoading}
          />
        ) : (
          <AssessmentsSummaryTable
            view={view}
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
            strandRows={strandRows}
            strandTotal={strandTotal}
            strandHasMore={strandRowsQ.hasNextPage}
            strandFetchingMore={strandRowsQ.isFetchingNextPage}
            onStrandFetchMore={() => void strandRowsQ.fetchNextPage()}
            strandSort={strandSort}
            strandDir={strandDir}
            onStrandSort={onStrandSort}
            strandLoading={strandLoading}
            standards={stdQ.data?.standards ?? []}
            search={search}
            loading={headerLoading}
          />
        )}
        </div>
      </section>

      {/* Program (school-wide) reports — always-visible launcher buttons. */}
      <section className="space-y-2 pt-1">
        <h2 className="text-sm font-semibold text-foreground">Program reports</h2>
        <nav aria-label="Program reports" className="flex flex-wrap gap-2">
          {PROGRAM_REPORTS.map((r) => {
            const Icon = r.icon;
            return (
              <Button
                key={r.slug}
                asChild
                variant="outline"
                className="group h-10 flex-1 justify-start gap-2 sm:flex-none"
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
