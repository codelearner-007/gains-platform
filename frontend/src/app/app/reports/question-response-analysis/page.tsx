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
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import QuestionDetailTable from '@/components/app/modules/reports/qra/QuestionDetailTable';
import {
  StrandsTable,
  StandardsTable,
  SummaryByStandardsHeader,
} from '@/components/app/modules/reports/qra/Strands_StandardsTables';
import ActiveFilterBar from '@/components/app/modules/reports/shared/ActiveFilterBar';
import ReportSlicer from '@/components/app/modules/reports/shared/ReportSlicer';
import LoadingState from '@/components/app/modules/reports/shared/LoadingState';
import ErrorState from '@/components/app/modules/reports/shared/ErrorState';
import ReportCanvas from '@/components/app/modules/reports/shared/ReportCanvas';
import AlignmentEmptyState from '@/components/app/modules/reports/shared/AlignmentEmptyState';
import { useReportFilters } from '@/lib/reports/filters';
import { deriveQra } from '@/lib/reports/filter-helpers';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

export default function QuestionResponseAnalysisPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');

  useEffect(() => {
    if (!itemId) router.replace('/app/reports');
  }, [itemId, router]);

  const { schoolId } = useSelectedSchool();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.qra(itemId ?? '', schoolId ?? undefined),
    queryFn: () => reportsApi.qra(itemId as string, schoolId ?? undefined),
    enabled: !!itemId,
  });

  const {
    filters,
    setStrand,
    setStandard,
    clearStrands,
    reset,
    activeChips,
  } = useReportFilters();

  const filtered = useMemo(
    () => (data ? deriveQra(data, filters) : null),
    [data, filters],
  );

  // Slicer options are the distinct strands of the FULL (unfiltered) payload
  // so the slicer never collapses to only the strands left after a selection.
  const strandOptions = useMemo(() => {
    const seen = new Set<string>();
    const out: string[] = [];
    for (const r of data?.strands_rollup ?? []) {
      if (r.strand && !seen.has(r.strand)) {
        seen.add(r.strand);
        out.push(r.strand);
      }
    }
    return out.sort((a, b) => a.localeCompare(b));
  }, [data]);

  const selectedStrandsSet = useMemo(
    () => new Set(filters.strands),
    [filters.strands],
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
      <div className="mb-3 flex flex-col gap-2 print:hidden">
        <div className="flex items-start justify-between gap-2">
          <ReportBreadcrumb
            crumbs={assessmentCrumbs({
              label: data.assessment.item_name || data.assessment.item_id,
            })}
          />
          <ExportMenu
            kind="qra"
            payload={data}
            name={data.assessment.item_name}
            xlsxUrl={buildXlsxUrl('qra', {
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
          title="Question Response Analysis Interactive"
        />
      </div>

      <div className="mb-2" style={{ minHeight: 100 }}>
        <KpiStrip kpis={filtered.kpis} />
      </div>

      {strandOptions.length > 0 && (
        <div className="mb-2 print:hidden">
          <ReportSlicer
            label="Strand"
            options={strandOptions}
            selected={selectedStrandsSet}
            onToggle={setStrand}
            onClear={clearStrands}
          />
        </div>
      )}

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
            selectedStrands={filters.strands}
            onSelectStrand={setStrand}
          />
          <StandardsTable
            kpis={filtered.kpis}
            standards={filtered.standards_rollup}
            selectedStandards={filters.standards}
            onSelectStandard={setStandard}
          />
        </div>
      </div>

      <div>
        <QuestionDetailTable
          questions={filtered.questions_overall}
          itemId={itemId}
          onSelectStandard={setStandard}
          selectedStandards={filters.standards}
        />
      </div>
    </ReportCanvas>
  );
}
