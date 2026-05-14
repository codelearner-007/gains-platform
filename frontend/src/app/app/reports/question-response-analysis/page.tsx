'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import KpiStrip from '@/components/app/modules/reports/qra/KpiStrip';
import AssessmentReportHeader from '@/components/app/modules/reports/shared/AssessmentReportHeader';
import InstructorCard from '@/components/app/modules/reports/qra/InstructorCard';
import QuestionDetailTable from '@/components/app/modules/reports/qra/QuestionDetailTable';
import {
  StrandsTable,
  StandardsTable,
  SummaryByStandardsHeader,
} from '@/components/app/modules/reports/qra/Strands_StandardsTables';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';

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
  if (!data) return null;

  return (
    <ReportCanvas>
      <div className="mb-2">
        <AssessmentReportHeader
          assessment={data.assessment}
          title="Question Response Analysis"
        />
      </div>

      <div
        className="grid grid-cols-12 gap-2 mb-2"
        style={{ minHeight: 100 }}
      >
        <div className="col-span-3">
          <InstructorCard kpis={data.kpis} assessment={data.assessment} />
        </div>
        <div className="col-span-9">
          <KpiStrip kpis={data.kpis} />
        </div>
      </div>

      <div className="mb-0">
        <SummaryByStandardsHeader />
      </div>

      <div className="grid grid-cols-2 gap-2 mb-2">
        <StrandsTable kpis={data.kpis} strands={data.strands_rollup} />
        <StandardsTable kpis={data.kpis} standards={data.standards_rollup} />
      </div>

      <div>
        <QuestionDetailTable
          questions={data.questions_overall}
          incorrectChoices={data.incorrect_choices}
          itemId={itemId}
        />
      </div>
    </ReportCanvas>
  );
}
