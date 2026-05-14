import type { YTDPeriodInfo, YTDSchoolInfo } from '@/lib/reports/types';
import ReportPageHeader from '@/components/app/modules/reports/shared/ReportPageHeader';

interface PageHeaderProps {
  school: YTDSchoolInfo;
  period: YTDPeriodInfo;
  totalAssessments: number;
}

export default function PageHeader({
  school,
  period,
  totalAssessments,
}: PageHeaderProps) {
  const subtitleParts = [
    school.current_session ? `Academic year ${school.current_session}` : null,
    period.date_from && period.date_to
      ? `${period.date_from} – ${period.date_to}`
      : null,
    totalAssessments
      ? `${totalAssessments} assessment${totalAssessments === 1 ? '' : 's'}`
      : null,
  ].filter(Boolean) as string[];

  const subtitle =
    subtitleParts.length > 0
      ? subtitleParts.join(' • ')
      : 'Cross-assessment performance dashboard';

  return (
    <ReportPageHeader
      logoUrl={school.logo_url}
      title="Year-To-Date Performance"
      subtitle={subtitle}
      meta={school.name || undefined}
    />
  );
}
