'use client';

import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import type { StandardSummaryFilters } from '@/lib/reports/types';
import { useSummaryFilters } from '@/lib/reports/use-summary-filters';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import ReportBreadcrumb, {
  programCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import KpiStrip from '@/components/app/modules/reports/std-summary/KpiStrip';
import StandardCard from '@/components/app/modules/reports/std-summary/StandardCard';
import StandardsTable from '@/components/app/modules/reports/std-summary/StandardsTable';
import StandardsByStrandChart from '@/components/app/modules/reports/std-summary/StandardsByStrandChart';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';

export default function StandardSummaryPage() {
  const { filters, setFilters } = useSummaryFilters<StandardSummaryFilters>({
    basePath: '/app/reports/standard-summary',
  });

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
      <div className="mb-3 flex flex-col gap-2">
        <ReportBreadcrumb crumbs={programCrumbs('Standard Summary')} />
        <ReportTypeSwitcher group="program" />
      </div>

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

      {data.data_quality?.alignment_status === 'missing' ? (
        <AlignmentEmptyState
          quality={data.data_quality}
          reportLabel="Standard Summary"
        />
      ) : (
        <>
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
        </>
      )}
    </ReportCanvas>
  );
}
