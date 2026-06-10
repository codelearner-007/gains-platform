'use client';

import { useEffect } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import ReportBreadcrumb, {
  assessmentCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import PaginatedReportHeader from '@/components/app/modules/reports/paginated/PaginatedReportHeader';
import PaginatedKpiStrip from '@/components/app/modules/reports/paginated/PaginatedKpiStrip';
import PaginatedFooter from '@/components/app/modules/reports/paginated/PaginatedFooter';
import QraByStandardTeacherTable from '@/components/app/modules/reports/paginated/QraByStandardTeacherTable';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

export default function QraByStandardTeacherPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');

  useEffect(() => {
    if (!itemId) router.replace('/app/reports');
  }, [itemId, router]);

  const { schoolId } = useSelectedSchool();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.qraByStandardTeacher(itemId ?? '', schoolId ?? undefined),
    queryFn: () =>
      reportsApi.qraByStandardTeacher(itemId as string, schoolId ?? undefined),
    enabled: !!itemId,
  });

  if (!itemId) return null;
  if (isLoading) return <LoadingState label="Loading report…" />;
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

  return (
    <ReportCanvas>
      <div className="mb-3 flex items-start justify-between gap-2 print:hidden">
        <ReportBreadcrumb
          crumbs={assessmentCrumbs({
            label: data.assessment.item_name || data.assessment.item_id,
          })}
        />
        <ExportMenu
          kind="qra-by-standard-teacher"
          payload={data}
          name={data.assessment.item_name}
        />
      </div>

      <div className="mb-2">
        <PaginatedReportHeader
          assessment={data.assessment}
          title="Question Response Analysis"
          subtitle="By Standard and by Classroom Instructor"
        />
      </div>

      <div className="mb-2">
        <PaginatedKpiStrip kpis={data.kpis} />
      </div>

      <QraByStandardTeacherTable standardGroups={data.standard_groups} />

      <PaginatedFooter />
    </ReportCanvas>
  );
}
