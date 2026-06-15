'use client';

import { useMemo } from 'react';
import type { StandardSummaryRollupRow } from '@/lib/reports/types';
import { performanceColor } from '@/lib/reports/colors';
import { formatPercent } from '@/lib/reports/format';
import RankedBarList, {
  type RankedBarRow,
} from '../shared/RankedBarList';

interface Props {
  rows: StandardSummaryRollupRow[];
}

/**
 * "Correct % by Standards" — one bar per standard, sorted best→worst. A school
 * can have hundreds of standards (343+ observed), so this renders as a
 * scrollable RankedBarList rather than a fixed-height recharts chart (which
 * crushed every bar/label into an illegible smear past ~45 categories).
 */
export default function StandardsBarChart({ rows }: Props) {
  const barRows = useMemo<RankedBarRow[]>(
    () =>
      rows
        .filter((r) => r.schoology_standard)
        .slice()
        .sort((a, b) => b.grade_average - a.grade_average)
        .map((r, i) => ({
          key: `${r.schoology_standard}-${r.strand}-${i}`,
          label: r.cpalms_standard || r.schoology_standard,
          sublabel: `(${r.num_questions} Q${r.num_questions === 1 ? '' : 's'})`,
          fraction: r.grade_average,
          valueLabel: formatPercent(r.grade_average, 1),
          color: performanceColor(r.grade_average),
          title: `${r.cpalms_standard || r.schoology_standard} · ${r.strand} · ${formatPercent(
            r.grade_average,
            1,
          )} correct · ${r.num_questions} questions · ${r.num_assessments} assessments`,
        })),
    [rows],
  );

  return (
    <RankedBarList
      title="Correct % by Standards"
      rows={barRows}
      emptyMessage="No standards match the current filters"
    />
  );
}
