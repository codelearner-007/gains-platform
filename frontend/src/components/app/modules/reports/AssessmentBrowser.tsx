'use client';

import { useState } from 'react';
import Link from 'next/link';
import { useQuery } from '@tanstack/react-query';
import { FileBarChart, Layers, type LucideIcon } from 'lucide-react';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import type { AssessmentFilters } from '@/lib/reports/types';
import { Button } from '@/components/ui/button';
import ReportFilters from './shared/ReportFilters';
import ErrorState from './shared/ErrorState';
import { Skeleton } from '@/components/ui/skeleton';

const ROW_ACTIONS: Array<{
  pathname: string;
  label: string;
  ariaPrefix: string;
  icon: LucideIcon;
}> = [
  {
    pathname: '/app/reports/question-response-analysis',
    label: 'QRA',
    ariaPrefix: 'Open Question Response Analysis for',
    icon: FileBarChart,
  },
  {
    pathname: '/app/reports/standards-deep-dive',
    label: 'SDD',
    ariaPrefix: 'Open Standards Deep Dive for',
    icon: Layers,
  },
];

export default function AssessmentBrowser() {
  const [filters, setFilters] = useState<AssessmentFilters>({});

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.assessments(filters),
    queryFn: () => reportsApi.assessments(filters),
  });

  return (
    <div className="space-y-4">
      <ReportFilters value={filters} onChange={setFilters} />

      <div className="bg-card border border-border rounded-lg overflow-hidden">
        <div className="px-4 py-3 border-b border-border bg-muted/40">
          <h3 className="text-sm font-semibold text-foreground">Assessments</h3>
          <p className="text-xs text-muted-foreground">
            {isLoading
              ? 'Loading…'
              : data
                ? `${data.length} result${data.length === 1 ? '' : 's'}`
                : ''}
          </p>
        </div>

        {isError ? (
          <div className="p-6">
            <ErrorState
              message={
                error instanceof Error
                  ? error.message
                  : 'Could not load assessments.'
              }
              onRetry={() => void refetch()}
            />
          </div>
        ) : isLoading ? (
          <div className="p-4 space-y-2">
            {Array.from({ length: 6 }).map((_, i) => (
              <Skeleton key={i} className="h-14 w-full" />
            ))}
          </div>
        ) : !data || data.length === 0 ? (
          <div className="p-8 text-center text-sm text-muted-foreground">
            No assessments found for the selected filters.
          </div>
        ) : (
          <ul className="divide-y divide-border">
            {data.map((row) => (
              <li
                key={row.item_id}
                className="flex flex-col sm:flex-row sm:items-center gap-3 px-4 py-3 hover:bg-accent/30 transition-colors"
              >
                <div className="flex-1 min-w-0">
                  <div className="text-sm font-medium text-foreground truncate">
                    {row.item_name ?? row.item_id}
                  </div>
                  <div className="mt-0.5 flex flex-wrap gap-x-3 gap-y-0.5 text-xs text-muted-foreground">
                    {row.subject && <span>{row.subject}</span>}
                    {row.grade && <span>{row.grade}</span>}
                    {row.section_name && (
                      <span>Section: {row.section_name}</span>
                    )}
                    {row.section_instructors && (
                      <span>{row.section_instructors}</span>
                    )}
                    {row.assessment_date && <span>{row.assessment_date}</span>}
                    {row.session && <span>{row.session}</span>}
                  </div>
                </div>

                <div className="flex items-center gap-1 shrink-0">
                  {ROW_ACTIONS.map((action) => {
                    const Icon = action.icon;
                    const name = row.item_name ?? row.item_id;
                    return (
                      <Button
                        key={action.pathname}
                        asChild
                        size="sm"
                        variant="ghost"
                        className="h-8 gap-1.5"
                      >
                        <Link
                          href={{
                            pathname: action.pathname,
                            query: { item_id: row.item_id },
                          }}
                          aria-label={`${action.ariaPrefix} ${name}`}
                        >
                          <Icon className="h-3.5 w-3.5" />
                          {action.label}
                        </Link>
                      </Button>
                    );
                  })}
                </div>
              </li>
            ))}
          </ul>
        )}
      </div>

      <p className="text-[11px] text-muted-foreground px-1">
        Need to drill into a specific incorrect answer? Open the assessment&apos;s
        Question Response Analysis, then click a question number in the Question
        Summary table.
      </p>
    </div>
  );
}
