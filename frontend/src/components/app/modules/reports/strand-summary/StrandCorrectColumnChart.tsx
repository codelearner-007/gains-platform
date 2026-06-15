'use client';

import { useMemo } from 'react';
import type { StrandSummaryStandardRow } from '@/lib/reports/types';
import { performanceColor } from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';
import RankedBarList, {
  type RankedBarRow,
} from '../shared/RankedBarList';

interface Props {
  rows: StrandSummaryStandardRow[];
}

/**
 * "Correct % per Standard" within one strand card. Rendered as a scrollable
 * RankedBarList (was a fixed-height vertical column chart whose angled x-labels
 * overlapped once a strand had more than a handful of standards).
 */
export default function StrandCorrectColumnChart({ rows }: Props) {
  const barRows = useMemo<RankedBarRow[]>(
    () =>
      rows
        .filter((r) => r.schoology_standard)
        .slice()
        .sort((a, b) => b.grade_average - a.grade_average)
        .map((r, i) => ({
          key: `${r.schoology_standard}-${i}`,
          label: r.schoology_standard,
          sublabel: `(${r.num_questions} Q${r.num_questions === 1 ? '' : 's'})`,
          fraction: r.grade_average,
          valueLabel: formatPercent(r.grade_average, 1),
          color: performanceColor(r.grade_average),
          title: `${r.schoology_standard} · ${formatPercent(r.grade_average, 1)} correct · ${r.num_questions} questions`,
        })),
    [rows],
  );

  return (
    <RankedBarList
      title="Correct % per Standard"
      rows={barRows}
      emptyMessage="No standards in this strand"
      maxHeight={360}
    />
  );
}
