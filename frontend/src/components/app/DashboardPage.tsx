'use client';

import Link from 'next/link';
import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import {
  useInfiniteQuery,
  useQuery,
  useQueryClient,
} from '@tanstack/react-query';
import { AlertCircle, ArrowUpRight } from 'lucide-react';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import { perfTextClass } from '@/lib/reports/colors';
import { getReportsByGroup } from '@/lib/reports/report-types';
import type { AssessmentFilters } from '@/lib/reports/types';
import { useDebounce } from '@/hooks/useDebounce';
import { StatCard } from '@/components/app/StatCard';
import { Button } from '@/components/ui/button';
import DashboardHeader from '@/components/app/dashboard/DashboardHeader';
import SearchInput from '@/components/app/dashboard/SearchInput';
import FilterPopover from '@/components/app/dashboard/FilterPopover';
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
  });

  // Grades feed the front grade chips.
  const gradesQ = useQuery({
    queryKey: reportsKeys.grades(schoolId ?? undefined),
    queryFn: () => reportsApi.grades(schoolId ?? undefined),
  });

  // Default the scope to the latest academic year, once per school; reset all
  // filter/search/sort state on a school switch.
  useEffect(() => {
    // Wait for the selected school to settle. effectiveSchoolId is null while
    // the accessible-schools list loads, then resolves to the real id with no
    // user action — running before that would init on the null id and then
    // re-reset (clobbering early user state + double-fetching) once it lands.
    if (schoolLoading) return;
    const list = sessionsQ.data;
    if (!list) return;
    const sid = schoolId ?? null;
    if (initedSchool.current === sid && inited) return;
    initedSchool.current = sid;
    autoDefault.current = { grade: false, subject: false };
    const latest = latestSession(list);
    setFilters(latest ? { session: latest } : {});
    setSearch('');
    setSort('date');
    setDir('desc');
    setStrandSort('date');
    setStrandDir('desc');
    setView('assessment');
    setStudentSort('name');
    setStudentDir('asc');
    setInited(true);
  }, [sessionsQ.data, schoolId, inited, schoolLoading]);

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
  });

  // standard-summary: header (name/logo/session) + KPI strip + school-wide
  // grade-average marker + the bounded "By Standard" table variant.
  const stdQ = useQuery({
    queryKey: reportsKeys.standardSummary(summaryFilters),
    queryFn: () => reportsApi.standardSummary(summaryFilters),
    enabled: inited,
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
    enabled: inited,
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
    enabled: inited,
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
    enabled: inited && view === 'student',
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

  // Default selection (once per school): pick the first available grade, then —
  // after the grade-scoped subject cards load — the first subject for that
  // grade. Staged because the cards (overviewQ) are grade-scoped, so the chosen
  // subject must come from the grade-scoped list to actually highlight a card.
  // Skips cleanly when a school has no grades/subjects, and is ref-gated so it
  // never fights a user deselect.
  useEffect(() => {
    if (!inited) return;
    if (!autoDefault.current.grade && gradesQ.data) {
      autoDefault.current.grade = true;
      if (grades.length > 0) {
        setFilters((f) => (f.grade ? f : { ...f, grade: grades[0] }));
        return; // let the grade-scoped overview load before picking a subject
      }
    }
    if (
      autoDefault.current.grade &&
      !autoDefault.current.subject &&
      overviewQ.data &&
      !overviewQ.isFetching
    ) {
      autoDefault.current.subject = true;
      const subs = overviewQ.data.subjects;
      if (subs.length > 0) {
        setFilters((f) => (f.subject ? f : { ...f, subject: subs[0].subject }));
      }
    }
  }, [inited, gradesQ.data, grades, overviewQ.data, overviewQ.isFetching]);

  const assessmentRows = useMemo(
    () => asmtQ.data?.pages.flatMap((p) => p.rows) ?? [],
    [asmtQ.data],
  );
  const assessmentTotal = asmtQ.data?.pages[0]?.total ?? 0;
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
  const studentBusy = studentLoading || (view === 'student' && studentFetching);

  const headerLoading = !inited || stdQ.isLoading;
  // In-flight (refetch) state — NOT a scroll fetch-more — for the two grids.
  const asmtFetching = asmtQ.isFetching && !asmtQ.isFetchingNextPage;
  const strandFetching = strandRowsQ.isFetching && !strandRowsQ.isFetchingNextPage;
  const asmtLoading = !inited || asmtQ.isPending;
  const asmtBusy = asmtLoading || asmtFetching;
  const strandLoading = !inited || strandRowsQ.isPending;
  const stdLoading = !inited || stdQ.isLoading;
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

  // Lock the click-filters (subject cards, grade chips, popover) while ANY
  // filter-dependent query is refetching, so rapid clicks can't interleave
  // requests or mix filters. Scroll fetch-more and the debounced search are
  // intentionally excluded (the search box stays typeable).
  const filtersBusy =
    overviewQ.isFetching ||
    stdQ.isFetching ||
    asmtFetching ||
    strandFetching ||
    studentFetching;

  // KPIs are computed at the per-question OVERALL grain (no section), so they
  // stay school-wide; flag that only when a section narrows the tables.
  const schoolWideHint = filters.section ? 'school-wide' : undefined;

  return (
    <div className="mx-auto max-w-7xl space-y-6">
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
            disabled={filtersBusy}
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
          disabled={filtersBusy}
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
          disabled={filtersBusy}
        />
      </section>

      {/* KPI strip (legacy KPI cardVisuals). Total Standards + Assessments are
          counts of the filtered sets and track every filter (incl. section).
          Total Students / Questions / Grade Average come from the per-question
          OVERALL cube, which — like legacy PowerBI — has no section grain, so
          they stay school-wide; marked "school-wide" when a section is active. */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard variant="plain" label="Total students" value={kpis?.total_students ?? '—'} hint={schoolWideHint} loading={headerLoading} />
        <StatCard variant="plain" label="Total standards" value={kpis?.total_standards ?? '—'} loading={headerLoading} />
        <StatCard variant="plain" label="Total questions" value={kpis?.total_questions ?? '—'} hint={schoolWideHint} loading={headerLoading} />
        <StatCard variant="plain" label="Assessments" value={asmtBusy ? '—' : assessmentTotal} loading={asmtBusy} />
        <StatCard
          variant="plain"
          label="Grade average"
          value={kpis?.grade_average_pct ?? '—'}
          valueClassName={kpis?.grade_average != null ? perfTextClass(kpis.grade_average) : ''}
          hint={schoolWideHint}
          loading={headerLoading}
        />
      </div>

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
            loading={stdLoading}
          />
        )}
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
