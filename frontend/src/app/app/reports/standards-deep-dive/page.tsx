'use client';

import { useMemo } from 'react';
import { useSearchParams } from 'next/navigation';
import { reportsApi, reportsKeys } from '@/lib/reports/api-client';
import AssessmentReportHeader from '@/components/app/modules/reports/shared/AssessmentReportHeader';
import ReportBreadcrumb, {
  assessmentCrumbs,
} from '@/components/app/modules/reports/shared/ReportBreadcrumb';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import KpiStrip from '@/components/app/modules/reports/sdd/KpiStrip';
import StrandTreemap from '@/components/app/modules/reports/sdd/StrandTreemap';
import StrandRowList from '@/components/app/modules/reports/sdd/StrandRowList';
import StandardRowList from '@/components/app/modules/reports/sdd/StandardRowList';
import PerformanceBandBars from '@/components/app/modules/reports/sdd/CorrectIncorrectBars';
import SectionHeader from '@/components/app/modules/reports/shared/SectionHeader';
import ActiveFilterBar from '@/components/app/modules/reports/shared/ActiveFilterBar';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';
import AssessmentReportShell from '@/components/app/modules/reports/shared/AssessmentReportShell';
import { useAssessmentReport } from '@/components/app/modules/reports/shared/useAssessmentReport';
import { useReportFilters } from '@/lib/reports/filters';
import { deriveSdd } from '@/lib/reports/filter-helpers';
import { getReportBySlug } from '@/lib/reports/report-types';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

const REPORT_NAME = getReportBySlug('standards-deep-dive').canonicalName;

/**
 * Standards Deep Dive interactive — layout mirrors the legacy PBIX page #16
 * (``data/_pbix_extract/50_sdd_spec.md``). Adds PowerBI-style click
 * cross-filtering: clicking a strand tile / standard row / band-chart
 * row filters every other panel on the page (except the Total Students
 * KPI, which is immune per ``08_relationships.csv:14``).
 */
export default function StandardsDeepDivePage() {
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');

  const { schoolId } = useSelectedSchool();

  const { data, isLoading, isError, error, refetch, ready } =
    useAssessmentReport({
      ready: !!itemId,
      queryKey: reportsKeys.sdd(itemId ?? '', schoolId ?? undefined),
      queryFn: () => reportsApi.sdd(itemId as string, schoolId ?? undefined),
    });

  const { filters, setStrand, setStandard, reset, activeChips } =
    useReportFilters();

  const filtered = useMemo(
    () => (data ? deriveSdd(data, filters) : null),
    [data, filters],
  );

  return (
    <AssessmentReportShell
      ready={ready}
      isLoading={isLoading}
      isError={isError}
      error={error}
      data={data}
      loadingLabel="Loading standards deep dive…"
      onRetry={() => void refetch()}
    >
      {(data) => {
        if (!itemId || !filtered) return null;
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
                  kind="sdd"
                  payload={data}
                  name={data.assessment.item_name}
                  xlsxUrl={buildXlsxUrl('sdd', {
                    itemId,
                    schoolId: schoolId ?? undefined,
                  })}
                />
              </div>
              <ReportTypeSwitcher group="assessment" itemId={itemId} />
            </div>

            <div className="mb-2">
              <AssessmentReportHeader
                assessment={data.assessment}
                title={REPORT_NAME}
              />
            </div>

            <div className="mb-2" style={{ minHeight: 100 }}>
              <KpiStrip kpis={filtered.kpis} />
            </div>

            <ActiveFilterBar
              chips={activeChips}
              onRemove={(chip) =>
                chip.key === 'strand'
                  ? setStrand(chip.value)
                  : setStandard(chip.value)
              }
              onClear={reset}
            />

            {data.data_quality?.alignment_status === 'missing' && (
              <AlignmentEmptyState
                quality={data.data_quality}
                reportLabel={REPORT_NAME}
                displayMode="banner"
              />
            )}

            <div className="mb-2">
              <SectionHeader title="Number of Standards by Strand" />
              <div className="grid grid-cols-1 md:grid-cols-2 gap-2 mt-2">
                <div className="min-w-0">
                  <StrandRowList
                    strands={filtered.strands_rollup}
                    selectedStrands={filters.strands}
                    onSelectStrand={setStrand}
                  />
                </div>
                <div className="min-w-0">
                  <StrandTreemap
                    strands={filtered.strands_rollup}
                    selectedStrands={filters.strands}
                    onSelectStrand={setStrand}
                  />
                </div>
              </div>
            </div>

            <div>
              <SectionHeader title="Standards by their performance" />
              <div className="grid grid-cols-1 md:grid-cols-12 gap-2 mt-2">
                <div className="md:col-span-3 min-w-0">
                  <StandardRowList
                    standards={filtered.standards_rollup}
                    selectedStandards={filters.standards}
                    onSelectStandard={setStandard}
                  />
                </div>
                <div className="md:col-span-9 min-w-0">
                  <PerformanceBandBars
                    bandHigh={filtered.band_high}
                    bandMid={filtered.band_mid}
                    bandLow={filtered.band_low}
                    selectedStandards={filters.standards}
                    onSelectStandard={setStandard}
                  />
                </div>
              </div>
            </div>
          </ReportCanvas>
        );
      }}
    </AssessmentReportShell>
  );
}
