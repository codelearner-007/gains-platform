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
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import ReportFilters from '@/components/app/modules/reports/shared/ReportFilters';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import PaginatedFooter from '@/components/app/modules/reports/paginated/PaginatedFooter';
import YtdLongitudinalMatrix, {
  type YtdVariant,
} from '@/components/app/modules/reports/paginated/YtdLongitudinalMatrix';
import { getReportBySlug } from '@/lib/reports/report-types';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';

const BASE_PATH = '/app/reports/year-to-date-performance';
const REPORT_NAME = getReportBySlug('year-to-date-performance').canonicalName;

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

  // Legacy YTD is always parameter-scoped (Grade × Subject × …) and paginated;
  // the whole-school unbounded matrix (hundreds of standard columns × every
  // student) is neither a legacy view nor renderable. Require Subject + Grade
  // before fetching/rendering — mirrors the legacy RDL's required parameters.
  const scoped = Boolean(filters.subject && filters.grade);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.ytd(queryFilters),
    queryFn: () => reportsApi.ytd(queryFilters),
    enabled: Boolean(schoolId) && scoped,
  });

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2 print:hidden">
        <div className="flex items-start justify-between gap-2">
          <ReportBreadcrumb crumbs={programCrumbs(REPORT_NAME)} />
          <ExportMenu
            kind="ytd"
            payload={data}
            name={data?.school.name || 'year-to-date'}
            xlsxUrl={buildXlsxUrl('ytd', {
              schoolId: schoolId ?? undefined,
              filters,
            })}
          />
        </div>
        <ReportTypeSwitcher group="program" />
        <ReportFilters value={filters} onChange={setFilters} />
        <VariantTabs active={variant} />
      </div>

      {!scoped ? (
        <ScopePrompt />
      ) : isLoading ? (
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
          <div className="mb-2">
            <ReportPageHeader
              logoUrl={data.school.logo_url}
              schoolName={data.school.name || undefined}
              title="Longitudinal Report - Year To Date"
              subtitle="Student Performance by Standards"
              meta={buildYtdMeta(
                data.assessment_type,
                data.subject,
                data.grade,
              )}
              variant="dense"
            />
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

// Legacy header-band SWITCH (RDL, identical in all 3 variants): Grade 6 / 7
// History are relabeled to World / US History under a "Lesson Assessments"
// type; every other scope renders "{assessment_type} | {subject} - {grade}".
function buildYtdMeta(
  assessmentType: string,
  subject: string,
  grade: string,
): string {
  const isHistory = subject === 'History';
  const type =
    isHistory && (grade === 'Grade 6' || grade === 'Grade 7')
      ? 'Lesson Assessments'
      : assessmentType;
  const subj =
    isHistory && grade === 'Grade 6'
      ? 'World History'
      : isHistory && grade === 'Grade 7'
        ? 'US History'
        : subject;
  return [type, [subj, grade].filter(Boolean).join(' - ')]
    .filter(Boolean)
    .join(' | ');
}

function ScopePrompt() {
  return (
    <div className="rounded-md border border-dashed p-8 text-center text-sm text-muted-foreground">
      Select a <span className="font-medium">Subject</span> and{' '}
      <span className="font-medium">Grade</span> above to view the year-to-date
      longitudinal matrix.
    </div>
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
