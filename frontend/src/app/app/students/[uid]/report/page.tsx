'use client';

import { useParams, useSearchParams } from 'next/navigation';
import { useQuery } from '@tanstack/react-query';
import { Printer } from 'lucide-react';

import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import ReportBreadcrumb from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import { Button } from '@/components/ui/button';
import PerStudentReport from '@/components/app/modules/students/PerStudentReport';

export default function StudentReportPage() {
  const params = useParams<{ uid: string }>();
  const search = useSearchParams();
  const uid = decodeURIComponent(params.uid);
  const session = search.get('session') ?? undefined;
  const schoolId = search.get('school_id') ?? undefined;

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.studentReport(uid, session, schoolId),
    queryFn: () => reportsApi.studentReport(uid, session, schoolId),
  });

  const dashboardHref = `/app${schoolId ? `?school_id=${schoolId}` : ''}`;

  return (
    <ReportCanvas>
      {/* Route-scoped print page: force A4 PORTRAIT for this report only. The
          global print stylesheet defaults @page to A4 landscape (for the wide
          QSR/QRA/YTD matrices); this in-body <style> is later in document order
          so it wins the @page cascade here, giving a portrait document with no
          size switch (a named page would emit a trailing blank landscape page). */}
      <style>{'@media print{@page{size:A4 portrait;margin:10mm}}'}</style>
      <div className="mb-3 flex items-center justify-between gap-2 print:hidden">
        <ReportBreadcrumb
          crumbs={[
            { label: 'Dashboard', href: dashboardHref },
            { label: data?.student.name ?? 'Student report' },
          ]}
        />
        <Button
          variant="outline"
          size="sm"
          className="gap-1.5"
          onClick={() => window.print()}
          disabled={!data || !data.has_data}
        >
          <Printer className="h-4 w-4" />
          Print / Save PDF
        </Button>
      </div>

      {isLoading ? (
        <LoadingState label="Loading student report…" />
      ) : isError ? (
        <ErrorState
          message={error instanceof Error ? error.message : 'Could not load the student report.'}
          onRetry={() => void refetch()}
        />
      ) : !data ? null : (
        <PerStudentReport data={data} />
      )}
    </ReportCanvas>
  );
}
