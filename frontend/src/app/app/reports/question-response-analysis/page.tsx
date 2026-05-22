'use client';

import { useEffect, useMemo } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import KpiStrip from '@/components/app/modules/reports/qra/KpiStrip';
import AssessmentReportHeader from '@/components/app/modules/reports/shared/AssessmentReportHeader';
import ReportBreadcrumb, {
  assessmentCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import QuestionDetailTable from '@/components/app/modules/reports/qra/QuestionDetailTable';
import {
  StrandsTable,
  StandardsTable,
  SummaryByStandardsHeader,
} from '@/components/app/modules/reports/qra/Strands_StandardsTables';
import ActiveFilterBar from '@/components/app/modules/reports/shared/ActiveFilterBar';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';
import { useReportFilters } from '@/lib/reports/filters';
import { deriveQra } from '@/lib/reports/filter-helpers';

export default function QuestionResponseAnalysisPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');

  useEffect(() => {
    if (!itemId) router.replace('/app/reports');
  }, [itemId, router]);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.qra(itemId ?? ''),
    queryFn: () => reportsApi.qra(itemId as string),
    enabled: !!itemId,
  });

  const { filters, setStrand, setStandard, reset, hasActiveFilter } =
    useReportFilters();

  const filtered = useMemo(
    () => (data ? deriveQra(data, filters) : null),
    [data, filters],
  );

  if (!itemId) return null;
  if (isLoading) return <LoadingState label="Loading assessment…" />;
  if (isError)
    return (
      <ErrorState
        message={
          error instanceof Error
            ? error.message
            : 'Could not load report.'
        }
        onRetry={() => void refetch()}
      />
    );
  if (!data || !filtered) return null;

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2">
        <ReportBreadcrumb
          crumbs={assessmentCrumbs({
            label: data.assessment.item_name || data.assessment.item_id,
          })}
        />
        <ReportTypeSwitcher group="assessment" itemId={itemId} />
      </div>

      <div className="mb-2">
        <AssessmentReportHeader
          assessment={data.assessment}
          title="Question Response Analysis Interactive"
        />
      </div>

      <div className="mb-2" style={{ minHeight: 100 }}>
        <KpiStrip kpis={filtered.kpis} />
      </div>

      {hasActiveFilter && (
        <ActiveFilterBar filters={filters} onClear={reset} />
      )}

      {data.data_quality?.alignment_status === 'missing' && (
        <AlignmentEmptyState
          quality={data.data_quality}
          reportLabel="Question Response Analysis Interactive"
          displayMode="banner"
        />
      )}

      <div className="flex flex-col gap-2 mb-2">
        <SummaryByStandardsHeader />
        <div className="grid grid-cols-1 md:grid-cols-2 gap-2">
          <StrandsTable
            kpis={filtered.kpis}
            strands={filtered.strands_rollup}
            selectedStrand={filters.strand}
            onSelectStrand={setStrand}
          />
          <StandardsTable
            kpis={filtered.kpis}
            standards={filtered.standards_rollup}
            selectedStandard={filters.standard}
            onSelectStandard={setStandard}
          />
        </div>
      </div>

      <div>
        <QuestionDetailTable
          questions={filtered.questions_overall}
          incorrectChoices={filtered.incorrect_choices}
          itemId={itemId}
        />
      </div>
    </ReportCanvas>
  );
}
