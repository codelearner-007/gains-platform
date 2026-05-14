import Link from 'next/link';
import { LineChart } from 'lucide-react';
import AssessmentBrowser from '@/components/app/modules/reports/AssessmentBrowser';
import { Button } from '@/components/ui/button';

export const metadata = {
  title: 'Reports',
};

export default function ReportsLandingPage() {
  return (
    <div className="max-w-6xl mx-auto space-y-6">
      <div className="flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
        <div className="space-y-1">
          <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
            Reports
          </p>
          <h1 className="text-2xl font-semibold tracking-tight text-foreground">
            Assessment Reports
          </h1>
          <p className="text-sm text-muted-foreground max-w-2xl">
            Pick an assessment below to drill into question-by-question
            performance and standards-level rollups, or open the
            cross-assessment Year-To-Date dashboard.
          </p>
        </div>
        <Button asChild variant="outline" size="sm">
          <Link href="/app/reports/year-to-date-performance">
            <LineChart className="mr-2 h-3.5 w-3.5" />
            Year-To-Date Performance
          </Link>
        </Button>
      </div>

      <AssessmentBrowser />
    </div>
  );
}
