import type {
  StrandSummaryRollupRow,
  StrandSummaryStandardRow,
} from '@/lib/reports/types';
import {
  LAYOUT_BORDER,
  STANDARD_HEADER_BG,
  STRAND_CHIP_BG,
  STRAND_CHIP_FG,
} from '@/lib/reports/colors';
import StrandIncorrectBarChart from './StrandIncorrectBarChart';
import StrandCorrectColumnChart from './StrandCorrectColumnChart';

interface StrandCardProps {
  strand: StrandSummaryRollupRow;
  standards: StrandSummaryStandardRow[];
}

export default function StrandCard({ strand, standards }: StrandCardProps) {
  const ownStandards = standards.filter((s) => s.strand === strand.strand);
  return (
    <div
      className="rounded-md border bg-card overflow-hidden"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="flex items-start justify-between gap-3 px-4 py-3 text-white"
        style={{ backgroundColor: STANDARD_HEADER_BG }}
      >
        <div className="min-w-0 flex-1">
          <div className="text-[11px] font-medium uppercase tracking-wider opacity-80">
            Strand
          </div>
          <div className="text-[15px] font-bold truncate">
            {strand.strand || 'Unnamed strand'}
          </div>
        </div>
        {strand.subjects.length > 0 && (
          <div className="flex flex-wrap items-center justify-end gap-1">
            {strand.subjects.map((s) => (
              <span
                key={s}
                className="rounded px-2 py-0.5 text-[10px] font-semibold"
                style={{ backgroundColor: STRAND_CHIP_BG, color: STRAND_CHIP_FG }}
              >
                {s}
              </span>
            ))}
          </div>
        )}
      </div>
      <div
        className="flex flex-wrap items-center gap-x-6 gap-y-1 border-b px-4 py-2 text-sm"
        style={{ borderColor: LAYOUT_BORDER }}
      >
        <div>
          <span className="text-neutral-600">Number of Standards: </span>
          <span className="font-semibold text-foreground">
            {strand.num_standards}
          </span>
        </div>
        <div>
          <span className="text-neutral-600">Number of Questions: </span>
          <span className="font-semibold text-foreground">
            {strand.num_questions}
          </span>
        </div>
        <div>
          <span className="text-neutral-600">Grade Avg: </span>
          <span className="font-semibold text-foreground">
            {strand.grade_average_pct}
          </span>
        </div>
      </div>
      <div className="grid grid-cols-1 gap-2 p-2 lg:grid-cols-2">
        <StrandIncorrectBarChart rows={ownStandards} />
        <StrandCorrectColumnChart rows={ownStandards} />
      </div>
    </div>
  );
}
