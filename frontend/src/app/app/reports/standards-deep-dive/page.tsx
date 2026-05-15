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
import KpiStrip from '@/components/app/modules/reports/sdd/KpiStrip';
import StrandTreemap from '@/components/app/modules/reports/sdd/StrandTreemap';
import {
  StrandsRollupTable,
  StandardsRollupTable,
} from '@/components/app/modules/reports/sdd/StandardsTable';
import PerformanceBandBars from '@/components/app/modules/reports/sdd/CorrectIncorrectBars';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';

export default function StandardsDeepDivePage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');

  useEffect(() => {
    if (!itemId) router.replace('/app/reports');
  }, [itemId, router]);

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.sdd(itemId ?? ''),
    queryFn: () => reportsApi.sdd(itemId as string),
    enabled: !!itemId,
  });

  if (!itemId) return null;
  if (isLoading) return <LoadingState label="Loading standards deep dive…" />;
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
          title="Standards Deep Dive"
        />
      </div>

      <div className="mb-2" style={{ minHeight: 100 }}>
        <KpiStrip kpis={data.kpis} />
      </div>

      {data.data_quality?.alignment_status === 'missing' ? (
        <AlignmentEmptyState
          quality={data.data_quality}
          reportLabel="Standards Deep Dive"
        />
      ) : (
        <>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mb-2">
            <StrandTreemap strands={data.strands_rollup} />
            <PerformanceBandBars
              bandHigh={data.band_high}
              bandMid={data.band_mid}
              bandLow={data.band_low}
            />
          </div>

          <div className="mb-2">
            <StrandsRollupTable strands={data.strands_rollup} />
          </div>

          <div>
            <StandardsRollupTable standards={data.standards_rollup} />
          </div>
        </>
      )}
    </ReportCanvas>
  );
}
