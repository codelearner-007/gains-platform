'use client';

import { useMemo } from 'react';
import Link from 'next/link';
import { useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';

import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import type { AssessmentFilters } from '@/lib/reports/types';
import { useSummaryFilters } from '@/lib/reports/use-summary-filters';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import ReportBreadcrumb, {
  programCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import PaginatedFooter from '@/components/app/modules/reports/paginated/PaginatedFooter';
import YtdLongitudinalMatrix, {
  type YtdVariant,
} from '@/components/app/modules/reports/paginated/YtdLongitudinalMatrix';
import { LAYOUT_BORDER } from '@/lib/reports/colors';

const BASE_PATH = '/app/reports/year-to-date-performance';

// Legacy YTD Longitudinal variants (PBIX ord 8/9/10). Same matrix payload;
// only the rendered columns differ — see YtdLongitudinalMatrix.
function parseVariant(raw: string | null): YtdVariant {
  if (raw === '2') return 2;
  if (raw === '3') return 3;
  return 1;
}

export default function YearToDatePerformancePage() {
  const searchParams = useSearchParams();
  const variant = parseVariant(searchParams.get('variant'));
  const { filters, setFilters } = useSummaryFilters<AssessmentFilters>({
    basePath: BASE_PATH,
    preserveParams: { variant: variant === 1 ? null : String(variant) },
  });
  const { schoolId } = useSelectedSchool();

  const queryFilters = useMemo<AssessmentFilters>(
    () => ({ ...filters, school_id: schoolId ?? undefined }),
    [filters, schoolId],
  );

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.ytd(queryFilters),
    queryFn: () => reportsApi.ytd(queryFilters),
  });

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2 print:hidden">
        <div className="flex items-start justify-between gap-2">
          <ReportBreadcrumb
            crumbs={programCrumbs('Year To Date - Longitudinal Report')}
          />
          <ExportMenu
            kind="ytd"
            payload={data}
            name={data?.school.name || 'year-to-date'}
          />
        </div>
        <ReportTypeSwitcher group="program" />
        <ReportFilters value={filters} onChange={setFilters} />
        <VariantTabs active={variant} />
      </div>

      {isLoading ? (
        <LoadingState label="Loading year-to-date longitudinal…" />
      ) : isError ? (
        <ErrorState
          message={
            error instanceof Error ? error.message : 'Could not load report.'
          }
          onRetry={() => void refetch()}
        />
      ) : !data ? null : (
        <>
          <div
            className="mb-2 bg-white border px-3 py-2"
            style={{ borderColor: LAYOUT_BORDER }}
          >
            <div className="text-[18px] font-bold text-black leading-tight">
              Longitudinal Report - Year To Date
            </div>
            <div className="text-[12px] text-neutral-700 leading-tight">
              Student Performance by Standards
            </div>
            <div className="text-[13px] text-black leading-tight">
              {[
                data.assessment_type,
                [data.subject, data.grade].filter(Boolean).join(' - '),
              ]
                .filter(Boolean)
                .join(' | ')}
            </div>
          </div>

          {data.standards.length === 0 ? (
            <EmptyState />
          ) : (
            <YtdLongitudinalMatrix payload={data} variant={variant} />
          )}

          <PaginatedFooter />
        </>
      )}
    </ReportCanvas>
  );
}

function EmptyState() {
  return (
    <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
      No standards were assessed for the selected session, grade, subject, and
      assessment type. Choose a different combination from the filters above.
    </div>
  );
}

function VariantTabs({ active }: { active: YtdVariant }) {
  const variants: { v: YtdVariant; label: string }[] = [
    { v: 1, label: 'Report 1' },
    { v: 2, label: 'Report 2' },
    { v: 3, label: 'Report 3' },
  ];
  const params = useSearchParams();
  return (
    <div role="tablist" className="flex gap-1 rounded-md bg-muted/50 p-1 w-fit">
      {variants.map(({ v, label }) => {
        const query = new URLSearchParams(params.toString());
        if (v === 1) query.delete('variant');
        else query.set('variant', String(v));
        const qs = query.toString();
        return (
          <Link
            key={v}
            href={qs ? `${BASE_PATH}?${qs}` : BASE_PATH}
            scroll={false}
            role="tab"
            aria-selected={active === v}
            className={`px-3 py-1.5 text-sm rounded transition-colors ${
              active === v
                ? 'bg-card text-primary shadow-sm font-medium'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            }`}
          >
            {label}
          </Link>
        );
      })}
    </div>
  );
}
