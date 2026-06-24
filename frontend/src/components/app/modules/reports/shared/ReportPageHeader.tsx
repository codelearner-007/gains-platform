import Image from 'next/image';
import { LAYOUT_BORDER } from '@/lib/reports/colors';

/**
 * Shared report page header — logo (or school-name text) on the left, title +
 * optional caption/subtitle/meta lines on the right.
 *
 * THE single header for every report view: the interactive QRA/SDD/IAD and the
 * paginated QSR/QRA-paginated/by-teacher/by-standard-teacher views all go
 * through `AssessmentReportHeader`; the program reports (Standard/Strand
 * Summary, YTD) call this component directly. The `dense` variant reproduces
 * the tighter paginated/print layout (smaller logo + title) so those views keep
 * their compact look while still showing the logo.
 *
 * Logo policy: a school logo is rendered ONLY when the school actually has a
 * `logo_url`. No school currently has one configured, so we must NOT fall back
 * to any specific school's logo (that previously showed Athenian's logo on
 * every school's reports). When there is no logo we show the school name as
 * text instead, so the report still identifies its school.
 *
 * The `unoptimized` flag on Next/Image is derived internally from the URL
 * scheme so remote logos bypass the optimiser (which is not configured for
 * arbitrary remote hosts) while local `/pilot/*.png` assets still go through
 * it.
 */

const isRemoteLogo = (url: string) => /^https?:\/\//i.test(url);

interface ReportPageHeaderProps {
  logoUrl: string | null;
  /** School name; shown as text in the logo's place when there is no logo. */
  schoolName?: string;
  title: string;
  /** Optional italic caption under the title (e.g. "By Classroom Instructor"). */
  caption?: string;
  subtitle?: string;
  meta?: string;
  /** `dense` = compact paginated/print layout (smaller logo + title). */
  variant?: 'default' | 'dense';
}

export default function ReportPageHeader({
  logoUrl,
  schoolName,
  title,
  caption,
  subtitle,
  meta,
  variant = 'default',
}: ReportPageHeaderProps) {
  const dense = variant === 'dense';
  const logoSize = dense ? 52 : 80;
  return (
    <div
      className={`flex items-center bg-white border ${
        dense ? 'gap-3 px-3 py-2' : 'gap-4 px-4 py-3'
      }`}
      style={{ borderColor: LAYOUT_BORDER }}
    >
      {logoUrl ? (
        <div className="flex-shrink-0">
          <Image
            src={logoUrl}
            alt={schoolName ? `${schoolName} logo` : title}
            width={logoSize}
            height={logoSize}
            priority
            unoptimized={isRemoteLogo(logoUrl)}
            style={{ width: logoSize, height: logoSize }}
            className="object-contain"
          />
        </div>
      ) : schoolName ? (
        <div
          className={`flex-shrink-0 max-w-[160px] font-bold text-black leading-tight ${
            dense ? 'text-[13px]' : 'text-[15px]'
          }`}
        >
          {schoolName}
        </div>
      ) : null}
      <div className="min-w-0 flex-1">
        <h1
          className={`font-bold text-black leading-tight ${
            dense ? 'text-[18px]' : 'text-[28px]'
          }`}
        >
          {title}
        </h1>
        {caption && (
          <div className="text-[12px] italic text-neutral-700 leading-snug">
            {caption}
          </div>
        )}
        {subtitle && (
          <div
            className={`text-black leading-snug ${
              dense ? 'text-[12px]' : 'mt-1 text-[14px]'
            }`}
          >
            {subtitle}
          </div>
        )}
        {meta && (
          <div className="text-[12px] text-neutral-700 leading-snug">
            {meta}
          </div>
        )}
      </div>
    </div>
  );
}
