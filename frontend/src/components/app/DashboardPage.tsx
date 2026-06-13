'use client';

import Link from 'next/link';
import { useEffect, useRef, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
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
import AssessmentsSummaryTable from '@/components/app/dashboard/AssessmentsSummaryTable';

const PROGRAM_REPORTS = getReportsByGroup('program');

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
  const [inited, setInited] = useState(false);
  const initedSchool = useRef<string | null>(null);

  // Sessions feed the default-year pick. Same query key as ReportFilters', so
  // react-query serves one shared request (no duplicate call).
  const sessionsQ = useQuery({
    queryKey: reportsKeys.sessions(schoolId ?? undefined),
    queryFn: () => reportsApi.sessions(schoolId ?? undefined),
  });

  // Default the scope to the latest academic year, once per school. Resets
  // filters + search on a school switch so each school opens on its newest year.
  useEffect(() => {
    const list = sessionsQ.data;
    if (!list) return;
    const sid = schoolId ?? null;
    if (initedSchool.current === sid && inited) return;
    initedSchool.current = sid;
    const latest = latestSession(list);
    setFilters(latest ? { session: latest } : {});
    setSearch('');
    setInited(true);
  }, [sessionsQ.data, schoolId, inited]);

  const summaryFilters = { ...filters, school_id: schoolId ?? undefined };

  // standard-summary is the single source for the header (school name/logo/
  // session), the KPI strip, the school-wide grade-average marker AND the
  // "By Standard" table variant. Gated on `inited` so the first fetch already
  // carries the default-year filter (no throwaway unfiltered request).
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
  const asmtQ = useQuery({
    queryKey: reportsKeys.assessmentSummaries(filters, schoolId ?? undefined),
    queryFn: () => reportsApi.assessmentSummaries(filters, schoolId ?? undefined),
    enabled: inited,
  });

  const kpis = stdQ.data?.kpis;
  const school = stdQ.data?.school;
  const schoolAverage = kpis?.grade_average ?? null;
  const assessments = asmtQ.data ?? [];
  const headerLoading = !inited || stdQ.isLoading;

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
        <StatCard label="Assessments" value={!inited || asmtQ.isLoading ? '—' : assessments.length} icon={BookOpen} loading={!inited || asmtQ.isLoading} />
        <StatCard label="Grade Average" value={kpis?.grade_average_pct ?? '—'} icon={Percent} loading={headerLoading} />
      </div>

      <AssessmentsSummaryTable
        schoolAverage={schoolAverage}
        assessments={assessments}
        standards={stdQ.data?.standards ?? []}
        strands={strandQ.data?.strands_rollup ?? []}
        search={search}
        loading={!inited || stdQ.isLoading || strandQ.isLoading || asmtQ.isLoading}
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
