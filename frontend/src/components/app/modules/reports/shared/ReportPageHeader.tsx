import Image from 'next/image';
import { FALLBACK_LOGO } from '@/lib/reports/format';
import { LAYOUT_BORDER } from '@/lib/reports/colors';

/**
 * Shared report page header — logo on the left, title + optional subtitle
 * and meta lines on the right.
 *
 * Used by the QRA, SDD, and YTD report views. The QRA/SDD callers go through
 * `AssessmentReportHeader`; the YTD page calls this component directly.
 *
 * The `unoptimized` flag on Next/Image is derived internally from the URL
 * scheme so remote logos bypass the optimiser (which is not configured for
 * arbitrary remote hosts) while local `/pilot/*.png` assets still go through
 * it.
 */

const isRemoteLogo = (url: string) => /^https?:\/\//i.test(url);

interface ReportPageHeaderProps {
  logoUrl: string | null;
  title: string;
  subtitle?: string;
  meta?: string;
}

export default function ReportPageHeader({
  logoUrl,
  title,
  subtitle,
  meta,
}: ReportPageHeaderProps) {
  const finalLogo = logoUrl ?? FALLBACK_LOGO;

  return (
    <div
      className="flex items-center gap-4 px-4 py-3 bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div className="flex-shrink-0">
        <Image
          src={finalLogo}
          alt={title}
          width={80}
          height={80}
          priority
          unoptimized={isRemoteLogo(finalLogo)}
          className="object-contain"
        />
      </div>
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
