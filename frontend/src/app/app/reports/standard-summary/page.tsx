'use client';

import { useMemo } from 'react';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import type { StandardSummaryFilters } from '@/lib/reports/types';
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
import StandardCard from '@/components/app/modules/reports/std-summary/StandardCard';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';

const REPORT_NAME = getReportBySlug('standard-summary').canonicalName;

// Legacy PBIX page #14 is a per-(subject × standard) card template — one card
// per cPalms_Standard. It carries NO KPI-card strip, ranked bar, rollup table,
// or by-strand chart (those were non-legacy additions and are intentionally
// removed for parity). The card + the school filter bar are all that render.
export default function StandardSummaryPage() {
  const { filters, setFilters } = useSummaryFilters<StandardSummaryFilters>({
    basePath: '/app/reports/standard-summary',
  });
  const { schoolId } = useSelectedSchool();

  // Session defaults to the school's latest year (resolved on the frontend and
  // always sent) so the report shows a single, current year — not every year
  // pooled together — matching the "Academic year …" header.
  const { session: effectiveSession, sessionsPending } = useEffectiveSession(
    schoolId,
    filters.session,
  );

  const queryFilters = useMemo<StandardSummaryFilters>(
    () => ({ ...filters, session: effectiveSession, school_id: schoolId ?? undefined }),
    [filters, effectiveSession, schoolId],
  );

  const { data, isLoading, isError, error, refetch } = useQuery({
    // cardsOnly: the report renders only the card grid, so skip the KPI cube
    // reads (incl. the total_students fact scan) — the dashboard fetches the
    // full KPI block separately.
    queryKey: reportsKeys.standardSummary(queryFilters, true),
    queryFn: () => reportsApi.standardSummary(queryFilters, true),
    // Wait for the latest session to resolve so the first paint is the current
    // year, never a flash of all-years-pooled data.
    enabled: Boolean(effectiveSession),
  });

  if (isLoading || sessionsPending)
    return <LoadingState label="Loading standard summary…" />;
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

  const count = data.standards.length;
  const yearLabel = effectiveSession ?? data.school.current_session;
  const subtitle = yearLabel
    ? `Academic year ${yearLabel} • ${count} standards`
    : `${count} standards`;

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2 print:hidden">
        <div className="flex items-start justify-between gap-2">
          <ReportBreadcrumb crumbs={programCrumbs(REPORT_NAME)} />
          <ExportMenu
            kind="standard-summary"
            payload={data}
            name={data.school.name || 'standard-summary'}
            xlsxUrl={buildXlsxUrl('standard-summary', {
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

      <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-2">
        {count === 0 ? (
          <div className="col-span-full bg-white border border-border rounded p-6 text-center text-sm text-muted-foreground">
            No standards match the current filters.
          </div>
        ) : (
          data.standards.map((std, idx) => (
            <StandardCard
              key={`${std.schoology_standard}-${std.strand}-${idx}`}
              std={std}
            />
          ))
        )}
      </div>
    </ReportCanvas>
  );
}
