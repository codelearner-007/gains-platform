'use client';

import { useMemo } from 'react';
import type { StandardSummaryStrandCount } from '@/lib/reports/types';
import { performanceColor } from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';
import RankedBarList, {
  type RankedBarRow,
} from '../shared/RankedBarList';

interface Props {
  rows: StandardSummaryStrandCount[];
}

/**
 * "# of Standards by Strand" — one bar per strand sized by its standard count,
 * tinted by the strand's grade average. Scrollable RankedBarList so a broad
 * multi-subject view (many strands) stays legible instead of crowding a
 * fixed-height chart.
 */
export default function StandardsByStrandChart({ rows }: Props) {
  const barRows = useMemo<RankedBarRow[]>(() => {
    const present = rows.filter((r) => r.strand);
    const max = Math.max(1, ...present.map((r) => r.num_standards));
    return present
      .slice()
      .sort((a, b) => b.num_standards - a.num_standards)
      .map((r, i) => ({
        key: `${r.strand}-${i}`,
        label: r.strand,
        fraction: r.num_standards / max,
        valueLabel: String(r.num_standards),
        color: performanceColor(r.grade_average),
        title: `${r.strand} · ${r.num_standards} standards · ${r.num_questions} questions · Avg ${formatPercent(
          r.grade_average,
          1,
        )}`,
      }));
  }, [rows]);

  return (
    <RankedBarList
      title="# of Standards by Strand"
      rows={barRows}
      emptyMessage="No strand data available"
      maxHeight={360}
    />
  );
}
