import Image from 'next/image';
import { LAYOUT_BORDER } from '@/lib/reports/colors';

/**
 * Shared report page header — logo (or school-name text) on the left, title +
 * optional subtitle and meta lines on the right.
 *
 * Used by the QRA, SDD, and YTD report views. The QRA/SDD callers go through
 * `AssessmentReportHeader`; the YTD page calls this component directly.
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
  subtitle?: string;
  meta?: string;
}

export default function ReportPageHeader({
  logoUrl,
  schoolName,
  title,
  subtitle,
  meta,
}: ReportPageHeaderProps) {
  return (
    <div
      className="flex items-center gap-4 px-4 py-3 bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      {logoUrl ? (
        <div className="flex-shrink-0">
          <Image
            src={logoUrl}
            alt={schoolName ? `${schoolName} logo` : title}
            width={80}
            height={80}
            priority
            unoptimized={isRemoteLogo(logoUrl)}
            style={{ width: 80, height: 80 }}
            className="object-contain"
          />
        </div>
      ) : schoolName ? (
        <div className="flex-shrink-0 max-w-[160px] text-[15px] font-bold text-black leading-tight">
          {schoolName}
        </div>
      ) : null}
      <div className="min-w-0 flex-1">
        <h1 className="text-[28px] font-bold text-black leading-tight">
          {title}
        </h1>
        {subtitle && (
          <div className="mt-1 text-[14px] text-black leading-snug">
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
