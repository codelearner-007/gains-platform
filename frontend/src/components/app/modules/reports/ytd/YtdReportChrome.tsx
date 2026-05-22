import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import type { YTDSchoolInfo, YTDPeriodInfo } from '@/lib/reports/types';

interface YtdReportChromeProps {
  school: YTDSchoolInfo;
  period: YTDPeriodInfo;
}

export default function YtdReportChrome({
  school,
  period,
}: YtdReportChromeProps) {
  const assessmentTypeText = school.assessment_types.length
    ? school.assessment_types.join(', ')
    : '—';
  const courseUnitText = school.course_unit || '—';
  const sessionText = school.current_session
    ? `Academic Year ${school.current_session}`
    : '';
  const dateRange =
    period.date_from && period.date_to
      ? `${period.date_from} – ${period.date_to}`
      : '';

  return (
    <div className="flex flex-col gap-2">
      <div
        className="rounded-md border px-4 py-3"
        style={{ borderColor: LAYOUT_BORDER, backgroundColor: HEADER_BAR_BG }}
      >
        <div className="text-[11px] font-semibold uppercase tracking-wider text-neutral-700">
          Longitudinal Report
        </div>
        <div className="mt-0.5 text-[16px] font-bold text-black">
          Paginated PDF Report
          {sessionText ? ` | ${sessionText}` : ''}
          {dateRange ? ` | ${dateRange}` : ''}
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
        <ChromeCard label="Course + Unit" value={courseUnitText} />
        <ChromeCard label="Assessment Type" value={assessmentTypeText} />
      </div>
    </div>
  );
}

function ChromeCard({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="rounded-md border bg-card px-4 py-3"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div className="text-[11px] font-medium uppercase tracking-wider text-neutral-600">
        {label}
      </div>
      <div className="mt-1 text-[15px] font-semibold text-foreground">
        {value}
      </div>
    </div>
  );
}
