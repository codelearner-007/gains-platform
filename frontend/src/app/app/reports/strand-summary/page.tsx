'use client';

import { useMemo } from 'react';
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
import { getReportBySlug } from '@/lib/reports/report-types';
import ReportAdditionalInsights from '@/components/app/modules/reports/shared/ReportAdditionalInsights';
import KpiStrip from '@/components/app/modules/reports/strand-summary/KpiStrip';
import StrandCard from '@/components/app/modules/reports/strand-summary/StrandCard';
import StrandTreemap from '@/components/app/modules/reports/strand-summary/StrandTreemap';
import StrandRollupTable from '@/components/app/modules/reports/strand-summary/StrandRollupTable';
import StrandStandardsTable from '@/components/app/modules/reports/strand-summary/StrandStandardsTable';
import BandBars from '@/components/app/modules/reports/strand-summary/BandBars';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';

const BASE_PATH = '/app/reports/strand-summary';
const REPORT_NAME = getReportBySlug('strand-summary').canonicalName;

export default function StrandSummaryPage() {
  const { filters, setFilters } = useSummaryFilters<StrandSummaryFilters>({
    basePath: BASE_PATH,
  });
  const { schoolId } = useSelectedSchool();

  // Legacy parity: the Strand Summary is a non-interactive whole-school rollup
  // (PBIX ord 15) — no per-strand click cross-filter. Scope comes only from the
  // ReportFilters slicers below.
  const queryFilters: StrandSummaryFilters = useMemo(
    () => ({
      ...filters,
      school_id: schoolId ?? undefined,
    }),
    [filters, schoolId],
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

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2 print:hidden">
        <div className="flex items-start justify-between gap-2">
          <ReportBreadcrumb crumbs={programCrumbs(REPORT_NAME)} />
          <ExportMenu
            kind="strand-summary"
            payload={data}
            name={data.school.name || 'strand-summary'}
            xlsxUrl={buildXlsxUrl('strand-summary', {
              schoolId: schoolId ?? undefined,
              filters: { ...filters },
            })}
          />
        </div>
        <ReportTypeSwitcher group="program" />
      </div>

      <div className="mb-2">
        <ReportPageHeader
          logoUrl={data.school.logo_url}
          schoolName={data.school.name || undefined}
          title={REPORT_NAME}
          subtitle={subtitle}
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
          reportLabel={REPORT_NAME}
          displayMode="banner"
        />
      )}

      {/* Legacy zone — per-strand chart pair repeater (PBIX page-ord-15) */}
      <div className="flex flex-col gap-3">
        {data.strands_rollup.length === 0 ? (
          <div className="bg-white border border-border rounded p-6 text-center text-sm text-muted-foreground">
            No strands match the current filters.
          </div>
        ) : (
          data.strands_rollup.map((strand) => (
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
        <StrandTreemap rows={data.strands_rollup} />
        <StrandRollupTable strands={data.strands_rollup} />
        <BandBars
          bandHigh={data.band_high}
          bandMid={data.band_mid}
          bandLow={data.band_low}
        />
        <StrandStandardsTable standards={data.standards_rollup} />
      </ReportAdditionalInsights>
    </ReportCanvas>
  );
}
