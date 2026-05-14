'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import type { StrandSummaryFilters } from '@/lib/reports/types';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import KpiStrip from '@/components/app/modules/reports/strand-summary/KpiStrip';
import StrandTreemap from '@/components/app/modules/reports/strand-summary/StrandTreemap';
import StrandRollupTable from '@/components/app/modules/reports/strand-summary/StrandRollupTable';
import StrandStandardsTable from '@/components/app/modules/reports/strand-summary/StrandStandardsTable';
import BandBars from '@/components/app/modules/reports/strand-summary/BandBars';

const FILTER_KEYS = [
  'session',
  'subject',
  'grade',
  'category',
  'section',
] as const;

const SELECTED_PARAM = 'strand';

function readFilters(params: URLSearchParams): StrandSummaryFilters {
  const out: StrandSummaryFilters = {};
  for (const k of FILTER_KEYS) {
    const v = params.get(k);
    if (v) (out as Record<string, string>)[k] = v;
  }
  return out;
}

export default function StrandSummaryPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const filters = useMemo(() => readFilters(searchParams), [searchParams]);
  const selectedStrand = searchParams.get(SELECTED_PARAM) || null;

  const setFilters = useCallback(
    (next: StrandSummaryFilters) => {
      const params = new URLSearchParams();
      for (const k of FILTER_KEYS) {
        const v = next[k];
        if (v) params.set(k, v);
      }
      // Preserve the strand selection across filter changes
      if (selectedStrand) params.set(SELECTED_PARAM, selectedStrand);
      router.replace(
        params.size > 0
          ? `/app/reports/strand-summary?${params.toString()}`
          : '/app/reports/strand-summary',
      );
    },
    [router, selectedStrand],
  );

  const setSelectedStrand = useCallback(
    (strand: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (strand) params.set(SELECTED_PARAM, strand);
      else params.delete(SELECTED_PARAM);
      router.replace(
        params.size > 0
          ? `/app/reports/strand-summary?${params.toString()}`
          : '/app/reports/strand-summary',
      );
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
