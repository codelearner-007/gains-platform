'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import AssessmentReportHeader from '@/components/app/modules/reports/shared/AssessmentReportHeader';
import ReportBreadcrumb, {
  assessmentCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import QuestionContextCard from '@/components/app/modules/reports/iad/QuestionContextCard';
import KpiStrip from '@/components/app/modules/reports/iad/KpiStrip';
import DistractorTable from '@/components/app/modules/reports/iad/DistractorTable';
import DistractorChart from '@/components/app/modules/reports/iad/DistractorChart';
import StudentAttemptTable from '@/components/app/modules/reports/iad/StudentAttemptTable';

export default function IncorrectAnswerDetailsPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');
  const questionId = searchParams.get('question_id');

  useEffect(() => {
    if (!itemId || !questionId) router.replace('/app/reports');
  }, [itemId, questionId, router]);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.iad(itemId ?? '', questionId ?? ''),
    queryFn: () => reportsApi.iad(itemId as string, questionId as string),
    enabled: !!itemId && !!questionId,
  });

  if (!itemId || !questionId) return null;
  if (isLoading) return <LoadingState label="Loading question deep dive…" />;
  if (isError)
    return (
      <ErrorState
        message={
          error instanceof Error ? error.message : 'Could not load report.'
        }
        onRetry={() => void refetch()}
      />
    );
  if (!data) return null;

  return (
    <ReportCanvas>
      <div className="mb-3 flex flex-col gap-2">
        <ReportBreadcrumb
          crumbs={assessmentCrumbs(
            {
              label: data.assessment.item_name || data.assessment.item_id,
              href: `/app/reports/question-response-analysis?item_id=${itemId}`,
            },
            {
              label: `Question ${data.question.question_no || data.question.position_number}`,
            },
          )}
        />
        <ReportTypeSwitcher
          group="assessment"
          itemId={itemId}
          questionId={questionId}
        />
      </div>

      <div className="mb-2">
        <AssessmentReportHeader
          assessment={data.assessment}
          title="Incorrect Answer Details"
        />
      </div>

      <div className="mb-2">
        <QuestionContextCard question={data.question} />
      </div>

      <div className="mb-2" style={{ minHeight: 100 }}>
        <KpiStrip kpis={data.kpis} />
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-2">
        <DistractorTable rows={data.distractors} />
        <DistractorChart rows={data.distractors} />
      </div>

      <div>
        <StudentAttemptTable attempts={data.student_attempts} />
      </div>
    </ReportCanvas>
  );
}
