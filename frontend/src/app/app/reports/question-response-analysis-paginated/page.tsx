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
import PaginatedFooter from '@/components/app/modules/reports/paginated/PaginatedFooter';
import QraPaginatedTable from '@/components/app/modules/reports/paginated/QraPaginatedTable';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

export default function QraPaginatedPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');

  useEffect(() => {
    if (!itemId) router.replace('/app/reports');
  }, [itemId, router]);

  const { schoolId } = useSelectedSchool();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.qraPaginated(itemId ?? '', schoolId ?? undefined),
    queryFn: () => reportsApi.qraPaginated(itemId as string, schoolId ?? undefined),
    enabled: !!itemId,
  });

  if (!itemId) return null;
  if (isLoading) return <LoadingState label="Loading question response analysis…" />;
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
      <div className="mb-3 flex flex-col gap-2 print:hidden">
        <div className="flex items-start justify-between gap-2">
          <ReportBreadcrumb
            crumbs={assessmentCrumbs({
              label: data.assessment.item_name || data.assessment.item_id,
            })}
          />
          <ExportMenu
            kind="qra-paginated"
            payload={data}
            name={data.assessment.item_name}
            xlsxUrl={buildXlsxUrl('qra-paginated', {
              itemId,
              schoolId: schoolId ?? undefined,
            })}
          />
        </div>
        <ReportTypeSwitcher group="assessment" itemId={itemId} />
      </div>

      <div className="mb-2">
        <PaginatedReportHeader
          assessment={data.assessment}
          title="Question Response Analysis"
          showInstructorLine
        />
      </div>

      {/* Legacy QRA paginated PDF has no KPI strip — intentionally omitted. */}

      <QraPaginatedTable questions={data.questions} />

      <PaginatedFooter />
    </ReportCanvas>
  );
}
