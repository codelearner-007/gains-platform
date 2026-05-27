import type { PaginatedKpis } from '@/lib/reports/types';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';
import { formatNumber } from '@/lib/reports/format';

interface Props {
  kpis: PaginatedKpis;
}

function Cell({ label, value }: { label: string; value: string }) {
  return (
    <div
      className="flex-1 px-3 py-1.5 border-r last:border-r-0 flex flex-col items-center justify-center text-center"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div className="text-[10px] text-neutral-700 uppercase tracking-wider">
        {label}
      </div>
      <div className="text-[18px] font-bold text-black tabular-nums leading-tight">
        {value}
      </div>
    </div>
  );
}

export default function PaginatedKpiStrip({ kpis }: Props) {
  return (
    <div
      className="w-full flex bg-white border"
      style={{ borderColor: LAYOUT_BORDER, backgroundColor: HEADER_BAR_BG }}
    >
      <Cell label="Total Questions" value={formatNumber(kpis.total_questions)} />
      <Cell label="Total Students" value={formatNumber(kpis.total_students)} />
      <Cell label="Score" value={formatNumber(kpis.score)} />
      <Cell
        label="Points Possible"
        value={formatNumber(kpis.total_possible_point)}
      />
      <Cell label="% Correct" value={kpis.grade_average_pct} />
    </div>
  );
}
