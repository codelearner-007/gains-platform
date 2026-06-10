'use client';

import { useCallback, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import type { StrandSummaryFilters } from '@/lib/reports/types';
import { useSummaryFilters } from '@/lib/reports/use-summary-filters';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import ReportBreadcrumb, {
  programCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import ReportAdditionalInsights from '@/components/app/modules/reports/shared/ReportAdditionalInsights';
import KpiStrip from '@/components/app/modules/reports/strand-summary/KpiStrip';
import StrandCard from '@/components/app/modules/reports/strand-summary/StrandCard';
import StrandTreemap from '@/components/app/modules/reports/strand-summary/StrandTreemap';
import StrandRollupTable from '@/components/app/modules/reports/strand-summary/StrandRollupTable';
import StrandStandardsTable from '@/components/app/modules/reports/strand-summary/StrandStandardsTable';
import BandBars from '@/components/app/modules/reports/strand-summary/BandBars';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';

const BASE_PATH = '/app/reports/strand-summary';
const SELECTED_PARAM = 'strand';

export default function StrandSummaryPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const selectedStrand = searchParams.get(SELECTED_PARAM) || null;

  const preserveParams = useMemo(
    () => ({ [SELECTED_PARAM]: selectedStrand }),
    [selectedStrand],
  );
  const { filters, setFilters } = useSummaryFilters<StrandSummaryFilters>({
    basePath: BASE_PATH,
    preserveParams,
  });
  const { schoolId } = useSelectedSchool();

  const setSelectedStrand = useCallback(
    (strand: string | null) => {
      const params = new URLSearchParams(searchParams.toString());
      if (strand) params.set(SELECTED_PARAM, strand);
      else params.delete(SELECTED_PARAM);
      router.replace(params.size > 0 ? `${BASE_PATH}?${params.toString()}` : BASE_PATH);
    },
    [router, searchParams],
  );

  const queryFilters: StrandSummaryFilters = useMemo(
    () => ({
      ...filters,
      strand: selectedStrand ?? undefined,
      school_id: schoolId ?? undefined,
    }),
    [filters, selectedStrand, schoolId],
  );

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.strandSummary(queryFilters),
    queryFn: () => reportsApi.strandSummary(queryFilters),
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

  const strandsToRender = selectedStrand
    ? data.strands_rollup.filter((s) => s.strand === selectedStrand)
    : data.strands_rollup;

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2 print:hidden">
        <div className="flex items-start justify-between gap-2">
          <ReportBreadcrumb crumbs={programCrumbs('Strand Summary')} />
          <ExportMenu
            kind="strand-summary"
            payload={data}
            name={data.school.name || 'strand-summary'}
            xlsxUrl={buildXlsxUrl('strand-summary', {
              schoolId: schoolId ?? undefined,
              filters: { ...filters, strand: selectedStrand ?? undefined },
            })}
          />
        </div>
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

      {data.data_quality?.alignment_status === 'missing' && (
        <AlignmentEmptyState
          quality={data.data_quality}
          reportLabel="Strand Summary"
          displayMode="banner"
        />
      )}

      {selectedStrand && (
        <div className="mb-2 flex items-center justify-between rounded-md border bg-muted/30 px-3 py-2 text-xs">
          <span>
            Filtered to strand:{' '}
            <span className="font-semibold">{selectedStrand}</span>
          </span>
          <button
            type="button"
            className="text-primary underline-offset-2 hover:underline"
            onClick={() => setSelectedStrand(null)}
          >
            Clear strand filter
          </button>
        </div>
      )}

      {/* Legacy zone — per-strand chart pair repeater (PBIX page-ord-15) */}
      <div className="flex flex-col gap-3">
        {strandsToRender.length === 0 ? (
          <div className="bg-white border border-border rounded p-6 text-center text-sm text-muted-foreground">
            No strands match the current filters.
          </div>
        ) : (
          strandsToRender.map((strand) => (
            <StrandCard
              key={strand.strand}
              strand={strand}
              standards={data.standards_rollup}
            />
          ))
        )}
      </div>

      {data.data_refreshed_at && (
        <div className="mt-3 text-right text-[11px] text-muted-foreground">
          Standard Info. Adopted/Revised Date: {data.data_refreshed_at}
        </div>
      )}

      <ReportAdditionalInsights>
        <StrandTreemap
          rows={data.strands_rollup}
          selectedStrand={selectedStrand}
          onSelectStrand={setSelectedStrand}
        />
        <StrandRollupTable
          strands={data.strands_rollup}
          selectedStrand={selectedStrand}
          onSelectStrand={setSelectedStrand}
        />
        <BandBars
          bandHigh={data.band_high}
          bandMid={data.band_mid}
          bandLow={data.band_low}
        />
        <StrandStandardsTable
          standards={data.standards_rollup}
          selectedStrand={selectedStrand}
        />
      </ReportAdditionalInsights>
    </ReportCanvas>
  );
}
