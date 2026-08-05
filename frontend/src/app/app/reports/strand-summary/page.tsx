'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import type {
  StrandSummaryFilters,
  StrandSummaryStandardRow,
} from '@/lib/reports/types';
import { useSummaryFilters } from '@/lib/reports/use-summary-filters';
import { useEffectiveSession } from '@/lib/reports/use-latest-session';
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
import StrandCard from '@/components/app/modules/reports/strand-summary/StrandCard';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';

const BASE_PATH = '/app/reports/strand-summary';
const REPORT_NAME = getReportBySlug('strand-summary').canonicalName;

// Legacy PBIX page #15 is a per-Strand tile repeater — strand banner, "# of
// questions"/"# of standards" text echoes, and a within-strand
// correct%-per-standard chart. It carries NO KPI-card strip, treemap, rollup
// table or band bars (those were non-legacy additions and are removed for
// parity). The tiles + the filter bar + the adopted-date footer are all that
// render.
export default function StrandSummaryPage() {
  const { filters, setFilters } = useSummaryFilters<StrandSummaryFilters>({
    basePath: BASE_PATH,
  });
  const { schoolId } = useSelectedSchool();

  // Session defaults to the school's latest year (resolved on the frontend and
  // always sent) so the report shows a single, current year — not every year
  // pooled together — matching the "Academic year …" header.
  const { session: effectiveSession, sessionsPending } = useEffectiveSession(
    schoolId,
    filters.session,
  );

  const queryFilters: StrandSummaryFilters = useMemo(
    () => ({ ...filters, session: effectiveSession, school_id: schoolId ?? undefined }),
    [filters, effectiveSession, schoolId],
  );

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.strandSummary(queryFilters),
    queryFn: () => reportsApi.strandSummary(queryFilters),
    // Wait for the latest session so the first paint is the current year.
    enabled: Boolean(effectiveSession),
  });

  // Pre-bucket the per-standard rows by strand once, so each StrandCard reads
  // its own slice instead of re-filtering the full list (avoids O(strands ×
  // standards) work in the repeater).
  const standardsByStrand = useMemo(() => {
    const map = new Map<string, StrandSummaryStandardRow[]>();
    for (const s of data?.standards_rollup ?? []) {
      const list = map.get(s.strand);
      if (list) list.push(s);
      else map.set(s.strand, [s]);
    }
    return map;
  }, [data?.standards_rollup]);

  if (isLoading || sessionsPending)
    return <LoadingState label="Loading strand summary…" />;
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

  const strandCount = data.strands_rollup.length;
  const standardCount = data.strands_rollup.reduce(
    (n, s) => n + s.num_standards,
    0,
  );
  const yearLabel = effectiveSession ?? data.school.current_session;
  const subtitle = yearLabel
    ? `Academic year ${yearLabel} • ${strandCount} strands • ${standardCount} standards`
    : `${strandCount} strands • ${standardCount} standards`;

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
              filters: { ...filters, session: effectiveSession },
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
        <ReportFilters
          value={filters}
          onChange={setFilters}
          showSection={false}
          resolvedSession={effectiveSession}
        />
      </div>

      {data.data_quality?.alignment_status === 'missing' && (
        <AlignmentEmptyState
          quality={data.data_quality}
          reportLabel={REPORT_NAME}
          displayMode="banner"
        />
      )}

      {/* Legacy per-strand tile repeater (PBIX page ord 15). */}
      <div className="flex flex-col gap-3">
        {strandCount === 0 ? (
          <div className="bg-white border border-border rounded p-6 text-center text-sm text-muted-foreground">
            No strands match the current filters.
          </div>
        ) : (
          data.strands_rollup.map((strand) => (
            <StrandCard
              key={strand.strand}
              strand={strand}
              standards={standardsByStrand.get(strand.strand) ?? []}
            />
          ))
        )}
      </div>

      {data.data_refreshed_at && (
        <div className="mt-3 text-right text-[11px] text-muted-foreground">
          Standard Info. Adopted/Revised Date: {data.data_refreshed_at}
        </div>
      )}
    </ReportCanvas>
  );
}
