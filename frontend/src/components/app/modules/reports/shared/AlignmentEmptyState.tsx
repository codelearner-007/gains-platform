'use client';

import { AlertTriangle, BookOpen } from 'lucide-react';
import type {
  AlignmentCause,
  AlignmentDataQuality,
} from '@/lib/reports/types';

interface AlignmentEmptyStateProps {
  /** The data_quality block from the report payload. */
  quality: AlignmentDataQuality;
  /** Label of the report we're rendering inside ("Standards Deep Dive" etc.) — used in the headline. */
  reportLabel: string;
}

/**
 * Copy shown inside the empty-state card. Picked from `quality.cause`
 * so each root cause gets actionable, distinct messaging.
 */
export interface AlignmentEmptyStateVariant {
  headline: string;
  body: string;
  remediation: string;
  showUnmatched?: boolean;
}

/**
 * Pure helper exported for unit-testing. Given a `cause` and the report
 * label, returns the headline / body / remediation copy. Falls back to
 * the legacy "no standards alignment" copy when `cause` is null or
 * undefined (i.e. an older backend response that predates the field).
 */
export function variantFor(
  cause: AlignmentCause | null | undefined,
  reportLabel: string,
): AlignmentEmptyStateVariant {
  switch (cause) {
    case 'labels_not_mapped':
      return {
        headline: `${reportLabel} can't render — this assessment's standards labels don't match the CPALMS catalog.`,
        body: 'The teacher entered standards values in Schoology, but those labels are not recognized CPALMS standard codes.',
        remediation:
          'Edit the assessment in Schoology and replace the non-code labels with valid CPALMS standard codes (e.g., MA.912.AR.3.1).',
        showUnmatched: true,
      };
    case 'no_questions':
      return {
        headline: `${reportLabel} can't render — this assessment has no questions in the data set.`,
        body: 'No question rows were found for this item in the warehouse.',
        remediation:
          'Verify the assessment was exported correctly from Schoology and reloaded into the data pipeline.',
      };
    case 'no_standards_in_source':
    case 'partial_teacher_alignment':
    case 'full_alignment':
    default:
      return {
        headline: `${reportLabel} can't render — this assessment has no standards alignment.`,
        body:
          'The Schoology source export for this assessment does not include any aligned learning objectives.',
        remediation:
          'Open this assessment in Schoology, edit each question, and use "Align Learning Objective" to attach the relevant standards. Re-export afterwards.',
      };
  }
}

export default function AlignmentEmptyState({
  quality,
  reportLabel,
}: AlignmentEmptyStateProps) {
  const {
    questions_total,
    questions_with_alignment,
    items_total,
    items_with_alignment,
    remediation_hint,
    cause,
    unmatched_labels,
  } = quality;
  const perItem = items_total <= 1;

  // When the backend provides a `cause`, use tailored copy. Otherwise
  // fall back to the legacy single-assessment / aggregate-scope headline
  // and the backend-supplied `remediation_hint` so older callers behave
  // exactly as before.
  const hasCause = cause !== undefined && cause !== null;
  const variant = variantFor(cause, reportLabel);

  const headline = hasCause
    ? variant.headline
    : perItem
      ? `${reportLabel} can't render — this assessment has no standards alignment.`
      : `${reportLabel} can't render — no questions in scope are aligned to standards.`;

  const remediation = hasCause ? variant.remediation : remediation_hint;

  const unmatched = (unmatched_labels ?? []).slice(0, 5);
  const showUnmatched =
    hasCause && variant.showUnmatched === true && unmatched.length > 0;

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

        {hasCause && (
          <p className="text-sm text-muted-foreground">{variant.body}</p>
        )}

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

        {showUnmatched && (
          <div className="w-full border-t border-border pt-4">
            <p className="text-sm font-medium text-foreground mb-2">
              Unrecognized labels in this assessment:
            </p>
            <ul className="flex flex-col gap-1 text-sm text-muted-foreground">
              {unmatched.map((label) => (
                <li
                  key={label}
                  className="font-mono bg-muted px-2 py-1 rounded text-foreground inline-block w-fit"
                >
                  {label}
                </li>
              ))}
            </ul>
          </div>
        )}

        <div className="flex gap-3 items-start text-sm text-muted-foreground border-t border-border pt-4 w-full">
          <BookOpen className="h-4 w-4 mt-0.5 shrink-0" aria-hidden="true" />
          <p>{remediation}</p>
        </div>
      </div>
    </div>
  );
}
