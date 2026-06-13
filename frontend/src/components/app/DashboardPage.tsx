'use client';

import Link from 'next/link';
import { useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowUpRight,
  BookOpen,
  GraduationCap,
  ListChecks,
  Percent,
  Settings,
  Shield,
  Users,
} from 'lucide-react';
import { useGlobal } from '@/lib/context/GlobalContext';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';
import { canSeeAdminEntry } from '@/lib/rbac/access';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import { getReportsByGroup } from '@/lib/reports/report-types';
import type { AssessmentFilters } from '@/lib/reports/types';
import { StatCard } from '@/components/app/StatCard';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import DashboardHeader from '@/components/app/dashboard/DashboardHeader';
import AssessmentsSummaryTable from '@/components/app/dashboard/AssessmentsSummaryTable';

const PROGRAM_REPORTS = getReportsByGroup('program');

export function DashboardPage() {
  const { user } = useGlobal();
  const { schoolId } = useSelectedSchool();
  const [filters, setFilters] = useState<AssessmentFilters>({});

  const showAdmin =
    !!user &&
    canSeeAdminEntry({
      permissions: user.app_metadata?.permissions ?? [],
      hierarchy_level: user.app_metadata?.hierarchy_level,
      user_role: user.app_metadata?.user_role,
    });

  // school_id is carried in the filter object for the summary endpoints; the
  // assessment-summaries endpoint takes it positionally.
  const summaryFilters = { ...filters, school_id: schoolId ?? undefined };

  // standard-summary is the single source for the header (school name/logo/
  // session), the KPI strip, the school-wide grade-average marker, AND the
  // "By Standard" table variant — one call, no duplication.
  const stdQ = useQuery({
    queryKey: reportsKeys.standardSummary(summaryFilters),
    queryFn: () => reportsApi.standardSummary(summaryFilters),
  });
  const strandQ = useQuery({
    queryKey: reportsKeys.strandSummary(summaryFilters),
    queryFn: () => reportsApi.strandSummary(summaryFilters),
  });
  const asmtQ = useQuery({
    queryKey: reportsKeys.assessmentSummaries(filters, schoolId ?? undefined),
    queryFn: () => reportsApi.assessmentSummaries(filters, schoolId ?? undefined),
  });

  const kpis = stdQ.data?.kpis;
  const school = stdQ.data?.school;
  const schoolAverage = kpis?.grade_average ?? null;
  const assessments = asmtQ.data ?? [];

  return (
    <div className="mx-auto max-w-7xl space-y-4">
      <DashboardHeader
        schoolName={school?.name ?? null}
        logoUrl={school?.logo_url ?? null}
        currentSession={school?.current_session ?? null}
        loading={stdQ.isLoading}
      />

      <ReportFilters value={filters} onChange={setFilters} />

      {/* School-scoped KPI strip (legacy KPI cardVisuals) */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        <StatCard label="Total Students" value={kpis?.total_students ?? '—'} icon={Users} loading={stdQ.isLoading} />
        <StatCard label="Total Standards" value={kpis?.total_standards ?? '—'} icon={GraduationCap} loading={stdQ.isLoading} />
        <StatCard label="Total Questions" value={kpis?.total_questions ?? '—'} icon={ListChecks} loading={stdQ.isLoading} />
        <StatCard label="Assessments" value={asmtQ.isLoading ? '—' : assessments.length} icon={BookOpen} loading={asmtQ.isLoading} />
        <StatCard label="Grade Average" value={kpis?.grade_average_pct ?? '—'} icon={Percent} loading={stdQ.isLoading} />
      </div>

      <AssessmentsSummaryTable
        schoolAverage={schoolAverage}
        assessments={assessments}
        standards={stdQ.data?.standards ?? []}
        strands={strandQ.data?.strands_rollup ?? []}
        loading={stdQ.isLoading || strandQ.isLoading || asmtQ.isLoading}
      />

      {/* Program reports (no per-assessment context) + management entries */}
      <section className="space-y-3 pt-1">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Program reports
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
          {PROGRAM_REPORTS.map((r) => (
            <QuickLink
              key={r.slug}
              href={`/app/reports/${r.slug}`}
              icon={r.icon}
              title={r.canonicalName}
              description={r.menuHint}
            />
          ))}
          <QuickLink
            href="/app/user-settings"
            icon={Settings}
            title="Account settings"
            description="Profile, password, two-factor and sessions."
          />
          {showAdmin && (
            <QuickLink
              href="/admin"
              icon={Shield}
              title="Admin panel"
              description="Users, roles, permissions, schools and audit logs."
            />
          )}
        </div>
      </section>
    </div>
  );
}

function QuickLink({
  href,
  icon: Icon,
  title,
  description,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
}) {
  return (
    <Link
      href={href}
      className="group relative flex flex-col gap-3 rounded-xl border border-border bg-card p-5 transition-all hover:border-foreground/20 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
    >
      <div className="flex items-center justify-between">
        <div className="flex h-9 w-9 items-center justify-center rounded-md bg-primary-soft text-primary">
          <Icon className="h-4 w-4" />
        </div>
        <ArrowUpRight className="h-4 w-4 text-muted-foreground/50 transition-colors group-hover:text-primary" />
      </div>
      <div className="space-y-1">
        <h3 className="text-sm font-semibold text-foreground">{title}</h3>
        <p className="text-xs leading-relaxed text-muted-foreground">{description}</p>
      </div>
    </Link>
  );
}
