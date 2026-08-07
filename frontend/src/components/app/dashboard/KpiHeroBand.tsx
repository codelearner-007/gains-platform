'use client';

import type { LucideIcon } from 'lucide-react';
import { ClipboardList, GraduationCap, ListChecks, Users } from 'lucide-react';
import { Skeleton } from '@/components/ui/skeleton';

interface KpiHeroBandProps {
  gradeAveragePct: string;
  totalStudents: React.ReactNode;
  totalStandards: React.ReactNode;
  totalQuestions: React.ReactNode;
  totalAssessments: React.ReactNode;
  /** Per-assessment grade averages (0..1), chronological, for the loaded
   *  assessments — the hero "recent assessments" trend sparkline. */
  trend: number[];
  loading: boolean;
  /** "school-wide" note on the section-invariant metrics. */
  schoolWideHint?: string;
  /** Small note under the Grade average figure (e.g. "Excludes quizzes"). */
  gradeAverageNote?: string;
}

/**
 * The dashboard's single focal surface: Grade Average rendered as a saturated
 * brand-gradient "hero" cell (big figure + a recent-assessments trend
 * sparkline over the loaded rows), with the
 * four count KPIs as hairline-divided neutral cells carrying a small muted
 * icon. This is the ONE place the brand gradient appears — everything else
 * stays neutral, so the band reads as the page's anchor without becoming slop.
 */
export default function KpiHeroBand({
  gradeAveragePct,
  totalStudents,
  totalStandards,
  totalQuestions,
  totalAssessments,
  trend,
  loading,
  schoolWideHint,
  gradeAverageNote,
}: KpiHeroBandProps) {
  return (
    <div className="overflow-hidden rounded-lg border border-border shadow-sm">
      <div className="flex flex-col md:flex-row">
        {/* Hero cell — Grade Average on the brand gradient. */}
        <div
          className="relative flex min-w-[13rem] flex-col justify-between gap-3 p-4 text-on-brand md:w-[26%] md:shrink-0"
          style={{ backgroundImage: 'var(--gradient-brand)' }}
        >
          <div>
            <p className="text-xs font-medium uppercase tracking-wide text-on-brand/70">
              Grade average
            </p>
            {loading ? (
              <Skeleton className="mt-1.5 h-9 w-24 bg-on-brand/25" />
            ) : (
              <p className="mt-0.5 text-4xl font-bold leading-none tabular-nums">
                {gradeAveragePct}
              </p>
            )}
            {gradeAverageNote && !loading && (
              <p className="mt-1 text-[11px] text-on-brand/70">{gradeAverageNote}</p>
            )}
            {schoolWideHint && !loading && (
              <p className="mt-1 text-[11px] text-on-brand/70">{schoolWideHint}</p>
            )}
          </div>
          {!loading && trend.length > 1 && <Sparkline values={trend} />}
        </div>

        {/* Count KPIs — neutral, hairline-divided. */}
        <dl className="grid flex-1 grid-cols-2 divide-x divide-y divide-border bg-card sm:grid-cols-4 sm:divide-y-0">
          <HeroStat icon={Users} label="Total students" value={totalStudents} hint={schoolWideHint} loading={loading} />
          <HeroStat icon={GraduationCap} label="Total standards" value={totalStandards} loading={loading} />
          <HeroStat icon={ListChecks} label="Total questions" value={totalQuestions} hint={schoolWideHint} loading={loading} />
          <HeroStat icon={ClipboardList} label="Assessments" value={totalAssessments} loading={loading} />
        </dl>
      </div>
    </div>
  );
}

function HeroStat({
  icon: Icon,
  label,
  value,
  hint,
  loading,
}: {
  icon: LucideIcon;
  label: string;
  value: React.ReactNode;
  hint?: string;
  loading: boolean;
}) {
  return (
    <div className="relative px-4 py-3.5">
      <Icon className="absolute right-3 top-3 h-4 w-4 text-muted-foreground/40" aria-hidden />
      {loading ? (
        <Skeleton className="h-7 w-14" />
      ) : (
        <dd className="text-2xl font-semibold leading-none tabular-nums text-foreground">
          {value}
        </dd>
      )}
      <dt className="mt-1.5 pr-5 text-xs font-medium text-muted-foreground">{label}</dt>
      {hint && !loading && (
        <p className="mt-0.5 text-[11px] text-muted-foreground/70">{hint}</p>
      )}
    </div>
  );
}

/** Inline SVG trend sparkline (white on the gradient) over the loaded rows. */
function Sparkline({ values }: { values: number[] }) {
  const w = 200;
  const h = 34;
  const pad = 2;
  const max = Math.max(...values, 0.001);
  const min = Math.min(...values);
  const span = Math.max(max - min, 0.001);
  const pts = values.map((v, i) => {
    const x = pad + (i / (values.length - 1)) * (w - pad * 2);
    const y = h - pad - ((v - min) / span) * (h - pad * 2);
    return [x, y] as const;
  });
  const line = pts.map(([x, y]) => `${x.toFixed(1)},${y.toFixed(1)}`).join(' ');
  const area = `${pts[0][0].toFixed(1)},${h} ${line} ${pts[pts.length - 1][0].toFixed(1)},${h}`;
  return (
    <svg
      viewBox={`0 0 ${w} ${h}`}
      className="h-8 w-full"
      preserveAspectRatio="none"
      aria-hidden
    >
      <polygon points={area} style={{ fill: 'var(--on-brand-faint)' }} />
      <polyline
        points={line}
        fill="none"
        style={{ stroke: 'var(--on-brand-strong)' }}
        strokeWidth={1.75}
        strokeLinejoin="round"
        strokeLinecap="round"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
