import Link from 'next/link';
import { ArrowUpRight } from 'lucide-react';
import AssessmentBrowser from '@/components/app/modules/reports/AssessmentBrowser';
import { Separator } from '@/components/ui/separator';
import {
  getReportsByGroup,
  buildHref,
  type ReportSlug,
} from '@/lib/reports/report-types';

export const metadata = {
  // Absolute so the landing tab reads "GAINS Reports", not "Reports | GAINS Reports".
  title: { absolute: 'GAINS Reports' },
};

// One-line descriptions keyed by slug. Names + icons + routes come from the
// report registry so the cards always match the rest of the app.
const PROGRAM_DESCRIPTIONS: Record<ReportSlug, string> = {
  'year-to-date-performance':
    'Longitudinal trend, grade distribution & most-improved students.',
  'standard-summary': 'School-wide standards rollup, grouped by strand.',
  'strand-summary': 'Strand rollup with treemap and per-standard drill-down.',
  // Assessment slugs are unused here but the record must be total.
  'question-response-analysis': '',
  'standards-deep-dive': '',
  'question-summary-paginated': '',
  'question-response-analysis-paginated': '',
  'question-response-analysis-by-teacher': '',
  'question-response-analysis-by-standard-and-teacher': '',
  'incorrect-answer-details': '',
};

const PROGRAM_REPORTS = getReportsByGroup('program').map((report) => ({
  href: buildHref(report.slug) as string,
  title: report.canonicalName,
  description: PROGRAM_DESCRIPTIONS[report.slug],
  icon: report.icon,
}));

export default function ReportsLandingPage() {
  return (
    <div className="mx-auto max-w-6xl space-y-8">
      <header className="space-y-1">
        <p className="text-xs font-medium uppercase tracking-wider text-muted-foreground">
          Reports
        </p>
        <h1 className="text-2xl font-semibold tracking-tight text-foreground">
          Pick a report
        </h1>
        <p className="max-w-2xl text-sm text-muted-foreground">
          Program Reports cover the whole school or session. Assessment Reports
          are scoped to a single assessment you select below.
        </p>
      </header>

      {/* Program Reports — one-click, school-wide. Kept at the top so they're
          never buried under the assessment list. */}
      <section aria-labelledby="program-reports-heading" className="space-y-3">
        <div className="flex items-baseline justify-between gap-3">
          <h2
            id="program-reports-heading"
            className="text-sm font-semibold tracking-tight text-foreground"
          >
            Program Reports
          </h2>
          <p className="text-xs text-muted-foreground">
            School- &amp; year-wide · no assessment needed
          </p>
        </div>

        <ul className="grid grid-cols-1 gap-3 sm:grid-cols-3">
          {PROGRAM_REPORTS.map((report) => {
            const Icon = report.icon;
            return (
              <li key={report.href}>
                <Link
                  href={report.href}
                  className="group flex h-full items-start gap-3 rounded-lg border border-border bg-card p-4 transition-all hover:border-foreground/20 hover:shadow-sm focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background"
                >
                  <div className="flex h-9 w-9 shrink-0 items-center justify-center rounded-md bg-primary-soft text-primary">
                    <Icon className="h-4 w-4" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="flex items-center justify-between gap-2">
                      <h3 className="truncate text-sm font-semibold text-foreground">
                        {report.title}
                      </h3>
                      <ArrowUpRight className="h-4 w-4 shrink-0 text-muted-foreground/50 transition-colors group-hover:text-primary" />
                    </div>
                    <p className="mt-0.5 text-xs leading-relaxed text-muted-foreground">
                      {report.description}
                    </p>
                  </div>
                </Link>
              </li>
            );
          })}
        </ul>
      </section>

      <Separator />

      <section aria-labelledby="assessment-reports-heading" className="space-y-4">
        <div className="space-y-0.5">
          <h2
            id="assessment-reports-heading"
            className="text-sm font-semibold tracking-tight text-foreground"
          >
            Assessment Reports
          </h2>
          <p className="text-xs text-muted-foreground">
            Filter to an assessment, then open a report from the menu.
          </p>
        </div>

        <AssessmentBrowser />
      </section>
    </div>
  );
}
