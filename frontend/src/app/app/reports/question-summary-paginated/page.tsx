'use client';

import { useEffect } from 'react';
import Link from 'next/link';
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
import QuestionSummaryMatrix from '@/components/app/modules/reports/paginated/QuestionSummaryMatrix';
import ReportTypeSwitcher from '@/components/app/modules/reports/shared/ReportTypeSwitcher';
import ExportMenu from '@/components/app/modules/reports/shared/ExportMenu';
import { buildXlsxUrl } from '@/lib/reports/export-xlsx';
import { useSelectedSchool } from '@/lib/context/SelectedSchoolContext';

// Legacy QSR paginated variants (PAG-4 / PAG-5, Decision 5):
//   • base     — PBIX ord 6 "Question Summary Report"
//   • teacher  — PBIX ord 7 "- Teacher" two-row per-instructor subtotal block
//   • redacted — PBIX ord 17, anonymized names (client-side; see matrix note)
// The invented "Header Highlights" variant is dropped, and the broken-in-legacy
// "Teacher Subtotal" report (ord 16) is intentionally NOT mirrored.
type Variant = 'base' | 'teacher' | 'redacted';

const VARIANT_LABEL: Record<Variant, string> = {
  base: 'Question Summary Report',
  teacher: 'Question Summary Report',
  redacted: 'Question Summary Report',
};

function parseVariant(raw: string | null): Variant {
  if (raw === 'teacher' || raw === 'redacted') return raw;
  return 'base';
}

export default function QuestionSummaryPaginatedPage() {
  const router = useRouter();
  const searchParams = useSearchParams();
  const itemId = searchParams.get('item_id');
  const variant = parseVariant(searchParams.get('variant'));

  useEffect(() => {
    if (!itemId) router.replace('/app/reports');
  }, [itemId, router]);

  const { schoolId } = useSelectedSchool();

  const { data, isLoading, isError, error, refetch } = useQuery({
    queryKey: reportsKeys.questionSummaryPaginated(itemId ?? '', schoolId ?? undefined),
    queryFn: () =>
      reportsApi.questionSummaryPaginated(itemId as string, schoolId ?? undefined),
    enabled: !!itemId,
  });

  if (!itemId) return null;
  if (isLoading) return <LoadingState label="Loading question summary…" />;
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
            kind="qsr"
            payload={data}
            name={data.assessment.item_name}
            xlsxUrl={buildXlsxUrl('qsr', {
              itemId,
              schoolId: schoolId ?? undefined,
            })}
          />
        </div>
        <ReportTypeSwitcher group="assessment" itemId={itemId} />
        <VariantTabs itemId={itemId} active={variant} />
      </div>

      <div className="mb-2">
        <PaginatedReportHeader
          assessment={data.assessment}
          title={VARIANT_LABEL[variant]}
        />
      </div>

      {/* PAG-3: legacy QSR has no KPI strip — intentionally omitted. */}

      <QuestionSummaryMatrix
        payload={data}
        showTeacherSubtotal={variant === 'teacher'}
        redacted={variant === 'redacted'}
      />

      <PaginatedFooter />
    </ReportCanvas>
  );
}

function VariantTabs({
  itemId,
  active,
}: {
  itemId: string;
  active: Variant;
}) {
  const variants: { slug: Variant; label: string }[] = [
    { slug: 'base', label: 'Base' },
    { slug: 'teacher', label: 'Teacher' },
    { slug: 'redacted', label: 'Redacted' },
  ];
  return (
    <div role="tablist" className="flex gap-1 rounded-md bg-muted/50 p-1 w-fit">
      {variants.map((v) => {
        const query: Record<string, string> = { item_id: itemId };
        if (v.slug !== 'base') query.variant = v.slug;
        return (
          <Link
            key={v.slug}
            href={{
              pathname: '/app/reports/question-summary-paginated',
              query,
            }}
            scroll={false}
            role="tab"
            aria-selected={active === v.slug}
            className={`px-3 py-1.5 text-sm rounded transition-colors ${
              active === v.slug
                ? 'bg-card text-primary shadow-sm font-medium'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            }`}
          >
            {v.label}
          </Link>
        );
      })}
    </div>
  );
}
