'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import type { StandardSummaryFilters } from '@/lib/reports/types';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import KpiStrip from '@/components/app/modules/reports/std-summary/KpiStrip';
import StandardCard from '@/components/app/modules/reports/std-summary/StandardCard';
import StandardsTable from '@/components/app/modules/reports/std-summary/StandardsTable';
import StandardsByStrandChart from '@/components/app/modules/reports/std-summary/StandardsByStrandChart';

const FILTER_KEYS = [
  'session',
  'subject',
  'grade',
  'category',
  'section',
] as const;

function readFilters(params: URLSearchParams): StandardSummaryFilters {
  const out: StandardSummaryFilters = {};
  for (const k of FILTER_KEYS) {
    const v = params.get(k);
    if (v) (out as Record<string, string>)[k] = v;
  }
  return out;
}

export default function StandardSummaryPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => readFilters(searchParams), [searchParams]);

  const setFilters = useCallback(
    (next: StandardSummaryFilters) => {
      const params = new URLSearchParams();
      for (const k of FILTER_KEYS) {
        const v = next[k];
        if (v) params.set(k, v);
      }
      router.replace(
        params.size > 0
          ? `/app/reports/standard-summary?${params.toString()}`
          : '/app/reports/standard-summary',
      );
    },
    [router],
  );

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.standardSummary(filters),
    queryFn: () => reportsApi.standardSummary(filters),
  });

  if (isLoading) return <LoadingState label="Loading standard summary…" />;
  if (isError) {
    return (
      <ErrorState
        message={
          error instanceof Error ? error.message : 'Could not load report.'
        }
        onRetry={() => void refetch()}
      />
    );
  }
  if (!data) return null;

  const subtitle = data.school.current_session
    ? `Academic year ${data.school.current_session} • ${data.kpis.total_standards} standards across ${data.strand_counts.length} strands`
    : `${data.kpis.total_standards} standards across ${data.strand_counts.length} strands`;

  return (
    <ReportCanvas>
      <div className="mb-2">
        <ReportPageHeader
          logoUrl={data.school.logo_url}
          title="Standard Summary"
          subtitle={subtitle}
          meta={data.school.name || undefined}
        />
      </div>

      <div className="mb-2">
        <ReportFilters value={filters} onChange={setFilters} />
      </div>

      <div className="mb-2" style={{ minHeight: 100 }}>
        <KpiStrip kpis={data.kpis} />
      </div>

      <div className="mb-2">
        <StandardsByStrandChart rows={data.strand_counts} />
      </div>

      <div className="mb-2">
        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
          {data.standards.length === 0 ? (
            <div className="col-span-full bg-white border border-border rounded p-6 text-center text-sm text-muted-foreground">
              No standards match the current filters.
            </div>
          ) : (
            data.standards.map((std, idx) => (
              <StandardCard
                key={`${std.cpalms_standard}-${std.schoology_standard}-${std.strand}-${idx}`}
                std={std}
              />
            ))
          )}
        </div>
      </div>

      <div>
        <StandardsTable standards={data.standards} />
      </div>
    </ReportCanvas>
  );
}
