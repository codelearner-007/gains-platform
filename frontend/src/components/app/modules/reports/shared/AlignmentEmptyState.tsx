'use client';

import { AlertTriangle, BookOpen } from 'lucide-react';
import type { AlignmentDataQuality } from '@/lib/reports/types';

interface AlignmentEmptyStateProps {
  /** The data_quality block from the report payload. */
  quality: AlignmentDataQuality;
  /** Label of the report we're rendering inside ("Standards Deep Dive" etc.) — used in the headline. */
  reportLabel: string;
}

export default function AlignmentEmptyState({
  quality,
  reportLabel,
}: AlignmentEmptyStateProps) {
  const { questions_total, questions_with_alignment, items_total, items_with_alignment, remediation_hint } =
    quality;
  const perItem = items_total <= 1;

  const headline = perItem
    ? `${reportLabel} can't render — this assessment has no standards alignment.`
    : `${reportLabel} can't render — no questions in scope are aligned to standards.`;

  return (
    <div className="w-full flex justify-center">
      <div
        className="bg-card border border-amber-300/60 rounded-lg p-8 flex flex-col items-start gap-5 shadow-sm"
        style={{ maxWidth: 720 }}
      >
        <div className="flex items-center gap-3">
          <AlertTriangle className="h-6 w-6 text-amber-500 shrink-0" aria-hidden="true" />
          <h2 className="text-lg font-semibold text-foreground">{headline}</h2>
        </div>

        <dl className="grid grid-cols-2 gap-x-6 gap-y-2 text-sm w-full">
          <dt className="text-muted-foreground">Questions in scope</dt>
          <dd className="font-medium text-foreground">
            {questions_with_alignment} of {questions_total} aligned
          </dd>
          {!perItem && (
            <>
              <dt className="text-muted-foreground">Assessments in scope</dt>
              <dd className="font-medium text-foreground">
                {items_with_alignment} of {items_total} with alignment
              </dd>
            </>
          )}
        </dl>

        <div className="flex gap-3 items-start text-sm text-muted-foreground border-t border-border pt-4 w-full">
          <BookOpen className="h-4 w-4 mt-0.5 shrink-0" aria-hidden="true" />
          <p>{remediation_hint}</p>
        </div>
      </div>
    </div>
  );
}
