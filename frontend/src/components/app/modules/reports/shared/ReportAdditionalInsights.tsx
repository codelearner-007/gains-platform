import { ReactNode } from 'react';
import { LAYOUT_BORDER } from '@/lib/reports/colors';

interface ReportAdditionalInsightsProps {
  children: ReactNode;
  subtitle?: string;
}

export default function ReportAdditionalInsights({
  children,
  subtitle,
}: ReportAdditionalInsightsProps) {
  return (
    <section
      aria-label="Additional Insights"
      className="mt-8 rounded-md border bg-muted/30"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <header
        className="border-b px-4 py-3"
        style={{ borderColor: LAYOUT_BORDER }}
      >
        <h2 className="text-sm font-semibold uppercase tracking-wide text-foreground">
          Additional Insights
        </h2>
        {subtitle && (
          <p className="text-xs text-muted-foreground">{subtitle}</p>
        )}
      </header>
      <div className="space-y-4 p-4">{children}</div>
    </section>
  );
}
