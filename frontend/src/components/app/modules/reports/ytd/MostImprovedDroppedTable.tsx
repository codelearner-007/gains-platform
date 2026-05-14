import { TrendingDown, TrendingUp } from 'lucide-react';
import type { YTDStudentSummary } from '@/lib/reports/types';
import { HEADER_BAR_BG, LAYOUT_BORDER } from '@/lib/reports/colors';

interface Props {
  mostImproved: YTDStudentSummary[];
  biggestDrops: YTDStudentSummary[];
}

function formatDelta(delta: number): string {
  const sign = delta >= 0 ? '+' : '';
  return `${sign}${(delta * 100).toFixed(1)}%`;
}

function StudentRow({
  student,
  variant,
}: {
  student: YTDStudentSummary;
  variant: 'up' | 'down';
}) {
  const Icon = variant === 'up' ? TrendingUp : TrendingDown;
  const color = variant === 'up' ? '#16a34a' : '#dc2626';
  return (
    <li className="flex items-center justify-between gap-2 px-2 py-1.5 border-b border-[#E5E5E5] last:border-b-0">
      <span className="text-[12px] text-black truncate" title={student.user_name}>
        {student.user_name}
      </span>
      <span
        className="flex items-center gap-1 text-[12px] font-semibold"
        style={{ color }}
      >
        <Icon className="h-3.5 w-3.5" />
        {formatDelta(student.delta)}
      </span>
    </li>
  );
}

export default function MostImprovedDroppedTable({
  mostImproved,
  biggestDrops,
}: Props) {
  return (
    <div
      className="flex flex-col bg-white border"
      style={{ borderColor: LAYOUT_BORDER }}
    >
      <div
        className="px-3 py-1.5 text-[14px] font-bold text-black"
        style={{ backgroundColor: HEADER_BAR_BG }}
      >
        Most Improved / Biggest Drops
      </div>
      <div className="grid grid-cols-2 divide-x divide-[#E5E5E5]">
        <div className="flex flex-col">
          <div className="px-3 py-1.5 text-[12px] font-semibold text-black bg-[#F5F5F5] border-b border-[#E5E5E5]">
            Most Improved
          </div>
          {mostImproved.length === 0 ? (
            <div className="p-3 text-[12px] text-neutral-500">
              No data
            </div>
          ) : (
            <ul>
              {mostImproved.map((s) => (
                <StudentRow
                  key={`up-${s.user_uid}`}
                  student={s}
                  variant="up"
                />
              ))}
            </ul>
          )}
        </div>
        <div className="flex flex-col">
          <div className="px-3 py-1.5 text-[12px] font-semibold text-black bg-[#F5F5F5] border-b border-[#E5E5E5]">
            Biggest Drops
          </div>
          {biggestDrops.length === 0 ? (
            <div className="p-3 text-[12px] text-neutral-500">
              No data
            </div>
          ) : (
            <ul>
              {biggestDrops.map((s) => (
                <StudentRow
                  key={`down-${s.user_uid}`}
                  student={s}
                  variant="down"
                />
              ))}
            </ul>
          )}
        </div>
      </div>
    </div>
  );
}
