import Image from 'next/image';
import type { AssessmentMeta } from '@/lib/reports/types';
import { LAYOUT_BORDER } from '@/lib/reports/colors';

interface Props {
  assessment: AssessmentMeta;
  title: string;
  subtitle?: string;
}

/**
 * Header strip for the paginated report family.
 *
 * Mirrors the seven PBIX chrome visuals (logo + H1 + H2 Course-and-Unit +
 * H2 Assessment-Type) at compressed proportions suitable for both screen
 * and print. The interactive reports use ``AssessmentReportHeader`` which
 * shares the same data — this variant trades the centered-title layout for
 * a print-friendly left-aligned bar.
 */
export default function PaginatedReportHeader({
  assessment,
  title,
  subtitle,
}: Props) {
  const grade = assessment.grade.replace(/^Grade\s+/i, '');
  const courseLine = `Course: ${grade}: ${assessment.item_name}`;
  return (
    <div
      className="bg-white border flex items-center gap-3 px-3 py-2"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      {assessment.school_logo_url ? (
        <div className="shrink-0 w-[64px] h-[64px] flex items-center justify-center">
          <Image
            src={assessment.school_logo_url}
            alt={`${assessment.school_name} logo`}
            width={64}
            height={64}
            className="object-contain"
            unoptimized
          />
        </div>
      ) : null}
      <div className="flex-1 min-w-0">
        <div className="text-[18px] font-bold text-black leading-tight">
          {title}
        </div>
        {subtitle && (
          <div className="text-[12px] italic text-neutral-700 leading-tight">
            {subtitle}
          </div>
        )}
        <div className="text-[13px] font-semibold text-black leading-tight mt-0.5 truncate">
          {courseLine}
        </div>
        <div className="text-[12px] text-neutral-700 leading-tight truncate">
          {assessment.assessment_type}
        </div>
      </div>
    </div>
  );
}
