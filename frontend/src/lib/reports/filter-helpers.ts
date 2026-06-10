import type {
  KPIs,
  QuestionOverall,
  QuestionResponseAnalysisPayload,
  SddBandStandardRow,
  SddKpis,
  SddStandardRow,
  SddStrandRow,
  StandardsDeepDivePayload,
} from './types';
import type { ReportFilters } from './filters';
import { formatPercent, splitStandards } from './format';

// Why client-side: `total_students` reads from `cube_school_summary` which
// has no relationship to `dim_strand` (08_relationships.csv:14, IsActive=0),
// so it must stay constant under any strand/standard filter. Encoding that
// rule once here avoids a round-trip-per-click and lets the rest of the
// dashboard recompute purely on the cached payload.

// Set-membership predicate: a row passes when
//   (strands empty OR row.strand ∈ strands) AND
//   (standards empty OR row.schoology_standard ∈ standards).
// Selecting standards also implies their parent strands so the strand-grain
// rollup narrows to the strands those standards belong to (mirrors PBIX, where
// picking a standard highlighted its strand).
function effectiveStrandSet(
  filters: ReportFilters,
  standards: readonly SddStandardRow[],
): Set<string> {
  const set = new Set(filters.strands);
  if (filters.standards.length > 0) {
    const wanted = new Set(filters.standards);
    for (const s of standards) {
      if (wanted.has(s.schoology_standard)) set.add(s.strand);
    }
  }
  return set;
}

interface SddDerived {
  kpis: SddKpis;
  strands_rollup: SddStrandRow[];
  standards_rollup: SddStandardRow[];
  band_high: SddBandStandardRow[];
  band_mid: SddBandStandardRow[];
  band_low: SddBandStandardRow[];
}

export function deriveSdd(
  payload: StandardsDeepDivePayload,
  filters: ReportFilters,
): SddDerived {
  if (filters.strands.length === 0 && filters.standards.length === 0) {
    return {
      kpis: payload.kpis,
      strands_rollup: payload.strands_rollup,
      standards_rollup: payload.standards_rollup,
      band_high: payload.band_high,
      band_mid: payload.band_mid,
      band_low: payload.band_low,
    };
  }

  const effectiveStrands = effectiveStrandSet(filters, payload.standards_rollup);
  const standardSet = new Set(filters.standards);
  const hasStrandFilter = effectiveStrands.size > 0;
  const hasStandardFilter = standardSet.size > 0;

  const matches = (row: { strand: string; schoology_standard?: string }) =>
    (!hasStrandFilter || effectiveStrands.has(row.strand)) &&
    (!hasStandardFilter ||
      (row.schoology_standard != null &&
        standardSet.has(row.schoology_standard)));

  const strandsRollup = payload.strands_rollup.filter(
    (r) => !hasStrandFilter || effectiveStrands.has(r.strand),
  );
  const standardsRollup = payload.standards_rollup.filter(matches);
  const bandHigh = payload.band_high.filter(matches);
  const bandMid = payload.band_mid.filter(matches);
  const bandLow = payload.band_low.filter(matches);

  // KPIs: total_students is immune; rest re-aggregate from filtered rows.
  // Single-selection keeps the server-computed strand/standard aggregate (it
  // carries rounding the questions-grain recompute would miss); multi-select
  // re-aggregates across the filtered rows.
  let totalQuestions = payload.kpis.total_questions;
  let totalStandards = payload.kpis.total_standards;
  let gradeAverage = payload.kpis.grade_average;

  if (standardsRollup.length > 0 && hasStandardFilter) {
    totalQuestions = standardsRollup.reduce((s, r) => s + r.num_questions, 0);
    totalStandards = standardsRollup.length;
    gradeAverage = weightedGradeAverage(standardsRollup);
  } else if (strandsRollup.length > 0 && hasStrandFilter) {
    totalQuestions = strandsRollup.reduce((s, r) => s + r.num_questions, 0);
    totalStandards = strandsRollup.reduce((s, r) => s + r.num_standards, 0);
    gradeAverage = weightedGradeAverage(strandsRollup);
  }

  const kpis: SddKpis = {
    ...payload.kpis,
    total_questions: totalQuestions,
    total_standards: totalStandards,
    grade_average: gradeAverage,
    grade_average_pct: formatPercent(gradeAverage, 1),
    // total_students intentionally unchanged (immunity rule).
  };

  return {
    kpis,
    strands_rollup: strandsRollup,
    standards_rollup: standardsRollup,
    band_high: bandHigh,
    band_mid: bandMid,
    band_low: bandLow,
  };
}

// Question-weighted mean of per-row grade averages (skips unassessed rows
// whose grade_average is null). Falls back to a single row's value, and to 0
// when nothing is assessed — matching the prior single-select KPI behaviour.
function weightedGradeAverage(
  rows: readonly { num_questions: number; grade_average: number | null }[],
): number {
  let weight = 0;
  let acc = 0;
  for (const r of rows) {
    if (r.grade_average == null) continue;
    const w = r.num_questions > 0 ? r.num_questions : 1;
    weight += w;
    acc += r.grade_average * w;
  }
  return weight > 0 ? acc / weight : 0;
}

// ─── QRA ─────────────────────────────────────────────────────────────────

interface QraDerived {
  kpis: KPIs;
  questions_overall: QuestionOverall[];
  strands_rollup: SddStrandRow[];
  standards_rollup: SddStandardRow[];
}

export function deriveQra(
  payload: QuestionResponseAnalysisPayload,
  filters: ReportFilters,
): QraDerived {
  if (filters.strands.length === 0 && filters.standards.length === 0) {
    return {
      kpis: payload.kpis,
      questions_overall: payload.questions_overall,
      strands_rollup: payload.strands_rollup,
      standards_rollup: payload.standards_rollup,
    };
  }

  const effectiveStrands = effectiveStrandSet(filters, payload.standards_rollup);
  const standardSet = new Set(filters.standards);
  const hasStrandFilter = effectiveStrands.size > 0;
  const hasStandardFilter = standardSet.size > 0;

  const strandsRollup = payload.strands_rollup.filter(
    (r) => !hasStrandFilter || effectiveStrands.has(r.strand),
  );
  const standardsRollup = payload.standards_rollup.filter(
    (r) =>
      (!hasStrandFilter || effectiveStrands.has(r.strand)) &&
      (!hasStandardFilter || standardSet.has(r.schoology_standard)),
  );

  // Question rows store all aligned Schoology codes (one per line) in
  // their `standards` field, so we split before matching against the
  // allowed-codes set derived from the (already filtered) rollup.
  const allowedSchoologyCodes = new Set(
    standardsRollup.map((r) => r.schoology_standard).filter(Boolean),
  );

  const questions = payload.questions_overall.filter((q) => {
    const codes = splitStandards(q.standards);
    return (
      codes.some((c) => allowedSchoologyCodes.has(c)) ||
      allowedSchoologyCodes.has(q.standard_raw)
    );
  });

  let totalPossible = 0;
  let totalScore = 0;
  let gradeSum = 0;
  let gradeCount = 0;
  let gradeMin = Number.POSITIVE_INFINITY;
  let gradeMax = Number.NEGATIVE_INFINITY;
  for (const q of questions) {
    totalPossible += q.total_possible_point ?? 0;
    totalScore += q.total_score ?? 0;
    if (Number.isFinite(q.grade_average)) {
      gradeSum += q.grade_average;
      gradeCount += 1;
      if (q.grade_average < gradeMin) gradeMin = q.grade_average;
      if (q.grade_average > gradeMax) gradeMax = q.grade_average;
    }
  }
  const gradeAverage = gradeCount > 0 ? gradeSum / gradeCount : 0;
  if (gradeCount === 0) {
    gradeMin = 0;
    gradeMax = 0;
  }

  const kpis: KPIs = {
    ...payload.kpis,
    total_questions: questions.length,
    total_standards: hasStandardFilter
      ? standardSet.size
      : standardsRollup.length,
    grade_average: gradeAverage,
    grade_average_pct: formatPercent(gradeAverage, 1),
    grade_min: gradeMin,
    grade_max: gradeMax,
    grade_min_pct: formatPercent(gradeMin, 1),
    grade_max_pct: formatPercent(gradeMax, 1),
    total_possible_point: totalPossible,
    total_score: totalScore,
  };

  return {
    kpis,
    questions_overall: questions,
    strands_rollup: strandsRollup,
    standards_rollup: standardsRollup,
  };
}
