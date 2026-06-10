'use client';

import Link from 'next/link';
import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ArrowUpRight,
  BookOpen,
  CalendarDays,
  GraduationCap,
  LineChart,
  ListChecks,
  Network,
  Settings,
  Shield,
} from 'lucide-react';
import { useGlobal } from '@/lib/context/GlobalContext';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';
import { canSeeAdminEntry } from '@/lib/rbac/access';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import { StatCard } from '@/components/app/StatCard';
import { Skeleton } from '@/components/ui/skeleton';

const QUICK_REPORTS = [
  {
    href: '/app/reports',
    icon: ListChecks,
    title: 'Assessment Reports',
    description: 'Browse, filter and open any per-assessment report.',
    primary: true,
  },
  {
    href: '/app/reports/year-to-date-performance',
    icon: LineChart,
    title: 'Year To Date',
    description: 'Longitudinal performance trend for the session.',
  },
  {
    href: '/app/reports/standard-summary',
    icon: GraduationCap,
    title: 'Standard Summary',
    description: 'School-wide standards rollup by strand.',
  },
  {
    href: '/app/reports/strand-summary',
    icon: Network,
    title: 'Strand Summary',
    description: 'Strand rollup with per-standard drill-down.',
  },
] as const;

export function DashboardPage() {
  const { loading, user } = useGlobal();
  const { schoolId, schools } = useSelectedSchool();

  const userName = user?.email?.split('@')[0] || 'there';
  const showAdmin =
    user &&
    canSeeAdminEntry({
      permissions: user.app_metadata?.permissions ?? [],
      hierarchy_level: user.app_metadata?.hierarchy_level,
      user_role: user.app_metadata?.user_role,
    });

  const schoolName =
    schools.find((s) => s.school_id === schoolId)?.name ?? null;

  const { data, isLoading: statsLoading } = useQuery({
    queryKey: reportsKeys.assessments({}, schoolId ?? undefined),
    queryFn: () => reportsApi.assessments({}, schoolId ?? undefined),
  });

  const stats = useMemo(() => {
    const rows = data ?? [];
    const distinct = (key: 'subject' | 'grade') =>
      new Set(rows.map((r) => r[key]).filter(Boolean)).size;
    const dates = rows.map((r) => r.assessment_date).filter(Boolean) as string[];
    return {
      assessments: rows.length,
      subjects: distinct('subject'),
      grades: distinct('grade'),
      latest: dates.length ? dates.slice().sort().at(-1) ?? null : null,
    };
  }, [data]);

  if (loading) {
    return (
      <div className="mx-auto max-w-6xl space-y-8">
        <div className="space-y-3">
          <Skeleton className="h-9 w-72" />
          <Skeleton className="h-4 w-96" />
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-16 rounded-lg" />
          ))}
        </div>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {Array.from({ length: 4 }).map((_, i) => (
            <Skeleton key={i} className="h-32 rounded-xl" />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-6xl space-y-8">
      {/* Header */}
      <header className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Dashboard
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Welcome back, {userName}
        </h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Assessment performance analytics
          {schoolName ? (
            <>
              {' '}
              for <span className="font-medium text-foreground">{schoolName}</span>
            </>
          ) : (
            ' across your schools'
          )}
          .
        </p>
      </header>

      {/* School-scoped KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard label="Assessments" value={stats.assessments} icon={ListChecks} loading={statsLoading} />
        <StatCard label="Subjects" value={stats.subjects} icon={BookOpen} loading={statsLoading} />
        <StatCard label="Grades" value={stats.grades} icon={GraduationCap} loading={statsLoading} />
        <StatCard label="Latest" value={stats.latest ?? '—'} icon={CalendarDays} loading={statsLoading} />
      </div>

      {/* Jump back in */}
      <section className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Jump back in
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {QUICK_REPORTS.map((item) => (
            <QuickLink key={item.href} {...item} />
          ))}
        </div>
      </section>

      {/* Manage */}
      <section className="space-y-3">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Manage
        </p>
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 lg:grid-cols-3">
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
  primary,
}: {
  href: string;
  icon: React.ComponentType<{ className?: string }>;
  title: string;
  description: string;
  primary?: boolean;
}) {
  return (
    <Link
      href={href}
      className={`group relative flex flex-col gap-3 rounded-xl border p-5 transition-all focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background ${
        primary
          ? 'border-primary/30 bg-primary-soft/40 hover:border-primary/50 hover:shadow-sm'
          : 'border-border bg-card hover:border-foreground/20 hover:shadow-sm'
      }`}
    >
      <div className="flex items-center justify-between">
        <div
          className={`flex h-9 w-9 items-center justify-center rounded-md ${
            primary
              ? 'bg-primary text-primary-foreground'
              : 'bg-primary-soft text-primary'
          }`}
        >
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
