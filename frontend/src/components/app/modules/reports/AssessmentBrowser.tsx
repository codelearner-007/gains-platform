'use client';

import { useEffect, useMemo, useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import {
  BookOpen,
  CalendarDays,
  ChevronDown,
  FileBarChart,
  FileText,
  GraduationCap,
  Grid3x3,
  Layers,
  ListChecks,
  Users,
  UsersRound,
  type LucideIcon,
} from 'lucide-react';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';
import type { AssessmentFilters, AssessmentListRow } from '@/lib/reports/types';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { StatCard } from '@/components/app/StatCard';
import ReportFilters from './shared/ReportFilters';
import ErrorState from './shared/ErrorState';
import { Skeleton } from '@/components/ui/skeleton';

const PAGE_SIZE = 12;

const ROW_ACTIONS: Array<{
  pathname: string;
  label: string;
  fullLabel: string;
  ariaPrefix: string;
  icon: LucideIcon;
}> = [
  {
    pathname: '/app/reports/question-response-analysis',
    label: 'QRA',
    fullLabel: 'Question Response Analysis',
    ariaPrefix: 'Open Question Response Analysis Interactive for',
    icon: FileBarChart,
  },
  {
    pathname: '/app/reports/standards-deep-dive',
    label: 'SDD',
    fullLabel: 'Standards Deep Dive',
    ariaPrefix: 'Open Standards Deep Dive interactive for',
    icon: Layers,
  },
  {
    pathname: '/app/reports/question-summary-paginated',
    label: 'QSR',
    fullLabel: 'Question Summary',
    ariaPrefix: 'Open Question Summary Report for',
    icon: Grid3x3,
  },
  {
    pathname: '/app/reports/question-response-analysis-paginated',
    label: 'QRA·P',
    fullLabel: 'QRA — Paginated',
    ariaPrefix: 'Open Question Response Analysis paginated for',
    icon: FileText,
  },
  {
    pathname: '/app/reports/question-response-analysis-by-teacher',
    label: 'QRA·T',
    fullLabel: 'QRA — by Teacher',
    ariaPrefix: 'Open Question Response Analysis by Teacher for',
    icon: Users,
  },
  {
    pathname: '/app/reports/question-response-analysis-by-standard-and-teacher',
    label: 'QRA·S·T',
    fullLabel: 'QRA — by Standard & Teacher',
    ariaPrefix: 'Open Question Response Analysis by Standard and Teacher for',
    icon: UsersRound,
  },
];

function distinctCount(rows: AssessmentListRow[], key: keyof AssessmentListRow) {
  return new Set(rows.map((r) => r[key]).filter(Boolean)).size;
}

export default function AssessmentBrowser() {
  const { schoolId } = useSelectedSchool();
  const [filters, setFilters] = useState<AssessmentFilters>({});
  const [visible, setVisible] = useState(PAGE_SIZE);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.assessments(filters, schoolId ?? undefined),
    queryFn: () => reportsApi.assessments(filters, schoolId ?? undefined),
  });

  // Collapse back to the first page whenever the result set changes
  // (new filter or a different school), so "Load more" never strands the
  // user deep in a list that no longer exists.
  useEffect(() => {
    setVisible(PAGE_SIZE);
  }, [filters, schoolId]);

  const rows = data ?? [];
  const stats = useMemo(() => {
    const dates = rows.map((r) => r.assessment_date).filter(Boolean) as string[];
    return {
      assessments: rows.length,
      subjects: distinctCount(rows, 'subject'),
      grades: distinctCount(rows, 'grade'),
      latest: dates.length ? dates.slice().sort().at(-1) ?? null : null,
    };
  }, [rows]);

  const shown = rows.slice(0, visible);
  const hasFilters = Object.values(filters).some(Boolean);

  return (
    <div className="space-y-4">
      {/* Filter-reactive KPI strip */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <StatCard
          label="Assessments"
          value={stats.assessments}
          icon={ListChecks}
          loading={isLoading}
        />
        <StatCard
          label="Subjects"
          value={stats.subjects}
          icon={BookOpen}
          loading={isLoading}
        />
        <StatCard
          label="Grades"
          value={stats.grades}
          icon={GraduationCap}
          loading={isLoading}
        />
        <StatCard
          label="Latest"
          value={stats.latest ?? '—'}
          icon={CalendarDays}
          loading={isLoading}
        />
      </div>

      <ReportFilters value={filters} onChange={setFilters} />

      <div className="overflow-hidden rounded-lg border border-border bg-card">
        <div className="flex items-center justify-between gap-3 border-b border-border bg-muted/40 px-4 py-3">
          <h3 className="text-sm font-semibold text-foreground">Assessments</h3>
          <p className="text-xs tabular-nums text-muted-foreground">
            {isLoading
              ? 'Loading…'
              : `Showing ${Math.min(shown.length, rows.length)} of ${rows.length}`}
          </p>
        </div>

        {isError ? (
          <div className="p-6">
            <ErrorState
              message={
                error instanceof Error ? error.message : 'Could not load assessments.'
              }
              onRetry={() => void refetch()}
            />
          </div>
        ) : isLoading ? (
          <div className="space-y-2 p-4">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : rows.length === 0 ? (
          <div className="p-10 text-center">
            <p className="text-sm font-medium text-foreground">No assessments found</p>
            <p className="mt-1 text-xs text-muted-foreground">
              {hasFilters
                ? 'Try adjusting or clearing the filters above.'
                : 'No assessments are available for this school yet.'}
            </p>
          </div>
        ) : (
          <>
            <ul className="divide-y divide-border">
              {shown.map((row) => (
                <AssessmentRow key={row.item_id} row={row} />
              ))}
            </ul>
            {visible < rows.length && (
              <div className="flex justify-center border-t border-border bg-muted/20 p-3">
                <Button
                  variant="outline"
                  size="sm"
                  onClick={() => setVisible((v) => v + PAGE_SIZE)}
                >
                  Load more
                  <span className="ml-1.5 text-xs text-muted-foreground">
                    ({rows.length - visible} left)
                  </span>
                </Button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}

function AssessmentRow({ row }: { row: AssessmentListRow }) {
  const name = row.item_name ?? row.item_id;
  return (
    <li className="flex flex-col gap-3 px-4 py-3 transition-colors hover:bg-accent/30 sm:flex-row sm:items-center">
      <div className="min-w-0 flex-1">
        <div className="truncate text-sm font-medium text-foreground">{name}</div>
        <div className="mt-1 flex flex-wrap items-center gap-x-2 gap-y-1 text-xs text-muted-foreground">
          {row.subject && (
            <Badge variant="secondary" className="font-normal">
              {row.subject}
            </Badge>
          )}
          {row.grade && <span>{row.grade}</span>}
          {row.section_name && <span>· {row.section_name}</span>}
          {row.section_instructors && <span>· {row.section_instructors}</span>}
          {row.assessment_date && (
            <span className="tabular-nums">· {row.assessment_date}</span>
          )}
        </div>
      </div>

      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="outline" size="sm" className="h-8 shrink-0 gap-1.5">
            Open report
            <ChevronDown className="h-3.5 w-3.5 text-muted-foreground" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end" className="w-64">
          <DropdownMenuLabel className="text-[11px] font-medium uppercase tracking-wider text-muted-foreground">
            Report type
          </DropdownMenuLabel>
          {ROW_ACTIONS.map((action) => {
            const Icon = action.icon;
            return (
              <DropdownMenuItem key={action.pathname} asChild>
                <Link
                  href={{ pathname: action.pathname, query: { item_id: row.item_id } }}
                  aria-label={`${action.ariaPrefix} ${name}`}
                  className="cursor-pointer"
                >
                  <Icon className="h-4 w-4 text-muted-foreground" />
                  <span className="flex-1 truncate">{action.fullLabel}</span>
                  <span className="text-[10px] font-medium tracking-wide text-muted-foreground">
                    {action.label}
                  </span>
                </Link>
              </DropdownMenuItem>
            );
          })}
        </DropdownMenuContent>
      </DropdownMenu>
    </li>
  );
}
