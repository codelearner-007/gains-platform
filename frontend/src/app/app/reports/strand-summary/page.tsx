'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import type { StrandSummaryFilters } from '@/lib/reports/types';
import { useSummaryFilters } from '@/lib/reports/use-summary-filters';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import ReportBreadcrumb from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import KpiStrip from '@/components/app/modules/reports/strand-summary/KpiStrip';
import StrandTreemap from '@/components/app/modules/reports/strand-summary/StrandTreemap';
import StrandRollupTable from '@/components/app/modules/reports/strand-summary/StrandRollupTable';
import StrandStandardsTable from '@/components/app/modules/reports/strand-summary/StrandStandardsTable';
import BandBars from '@/components/app/modules/reports/strand-summary/BandBars';

const BASE_PATH = '/app/reports/strand-summary';
const SELECTED_PARAM = 'strand';

export default function StrandSummaryPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedStrand = searchParams.get(SELECTED_PARAM) || null;

  // Preserve the strand selection across filter changes via the
  // useSummaryFilters preserveParams hook contract.
  const preserveParams = useMemo(
    () => ({ [SELECTED_PARAM]: selectedStrand }),
    [selectedStrand],
  );
  const { filters, setFilters } = useSummaryFilters<StrandSummaryFilters>({
    basePath: BASE_PATH,
    preserveParams,
  });

  const setSelectedStrand = useCallback(
    (strand: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (strand) params.set(SELECTED_PARAM, strand);
      else params.delete(SELECTED_PARAM);
      router.replace(params.size > 0 ? `${BASE_PATH}?${params.toString()}` : BASE_PATH);
    },
    [router, searchParams],
  );

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.strandSummary(filters),
    queryFn: () => reportsApi.strandSummary(filters),
  });

  if (isLoading) return <LoadingState label="Loading strand summary…" />;
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
    ? `Academic year ${data.school.current_session} • ${data.kpis.total_strands} strands • ${data.kpis.total_standards} standards`
    : `${data.kpis.total_strands} strands • ${data.kpis.total_standards} standards`;

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2">
        <ReportBreadcrumb
          crumbs={[
            { label: 'Reports', href: '/app/reports' },
            { label: 'Program Reports', href: '/app/reports' },
            { label: 'Strand Summary' },
          ]}
        />
        <ReportTypeSwitcher group="program" />
      </div>

      <div className="mb-2">
        <ReportPageHeader
          logoUrl={data.school.logo_url}
          title="Strand Summary"
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
        <StrandTreemap
          rows={data.strands_rollup}
          selectedStrand={selectedStrand}
          onSelectStrand={setSelectedStrand}
        />
      </div>

      <div className="mb-2">
        <StrandRollupTable
          strands={data.strands_rollup}
          selectedStrand={selectedStrand}
          onSelectStrand={setSelectedStrand}
        />
      </div>

      <div className="mb-2">
        <BandBars
          bandHigh={data.band_high}
          bandMid={data.band_mid}
          bandLow={data.band_low}
        />
      </div>

      <div>
        <StrandStandardsTable
          standards={data.standards_rollup}
          selectedStrand={selectedStrand}
        />
      </div>
    </ReportCanvas>
  );
}
