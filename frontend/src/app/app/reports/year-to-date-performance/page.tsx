'use client';

import { useQuery } from '@tanstack/react-query';
import { reportsApi, reportsKeys } from '@/lib/services/reports-service';
import PageHeader from '@/components/app/modules/reports/ytd/PageHeader';
import KpiStrip from '@/components/app/modules/reports/ytd/KpiStrip';
import OverallTrendChart from '@/components/app/modules/reports/ytd/OverallTrendChart';
import GradeDistributionChart from '@/components/app/modules/reports/ytd/GradeDistributionChart';
import StudentProgressionChart from '@/components/app/modules/reports/ytd/StudentProgressionChart';
import StrandHeatmap from '@/components/app/modules/reports/ytd/StrandHeatmap';
import MostImprovedDroppedTable from '@/components/app/modules/reports/ytd/MostImprovedDroppedTable';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';

export default function YearToDatePerformancePage() {
  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.ytd(),
    queryFn: () => reportsApi.ytd(),
  });

  if (isLoading) return <LoadingState label="Loading year-to-date performance…" />;
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
        <PageHeader
          school={data.school}
          period={data.period}
          totalAssessments={data.kpis.total_assessments}
        />
      </div>

      <div className="mb-2" style={{ minHeight: 100 }}>
        <KpiStrip kpis={data.kpis} />
      </div>

      <div className="grid grid-cols-12 gap-2 mb-2">
        <div className="col-span-12 lg:col-span-7">
          <OverallTrendChart timeline={data.timeline} />
        </div>
        <div className="col-span-12 lg:col-span-5">
          <GradeDistributionChart data={data.grade_distribution} />
        </div>
      </div>

      <div className="mb-2">
        <StrandHeatmap cells={data.strand_heatmap} />
      </div>

      <div className="grid grid-cols-12 gap-2">
        <div className="col-span-12 lg:col-span-8">
          <StudentProgressionChart data={data.student_progression} />
        </div>
        <div className="col-span-12 lg:col-span-4">
          <MostImprovedDroppedTable
            mostImproved={data.kpis.most_improved}
            biggestDrops={data.kpis.biggest_drops}
          />
        </div>
      </div>
    </ReportCanvas>
  );
}
