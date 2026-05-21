import type {
  IncorrectChoice,
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
import { formatPercent } from './format';

// Why client-side: `total_students` reads from `cube_school_summary` which
// has no relationship to `dim_strand` (08_relationships.csv:14, IsActive=0),
// so it must stay constant under any strand/standard filter. Encoding that
// rule once here avoids a round-trip-per-click and lets the rest of the
// dashboard recompute purely on the cached payload.

function pickStrandFromStandard(
  schoology: string,
  standards: readonly SddStandardRow[],
): string | undefined {
  return standards.find((s) => s.schoology_standard === schoology)?.strand;
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
  if (!filters.strand && !filters.standard) {
    return {
      kpis: payload.kpis,
      strands_rollup: payload.strands_rollup,
      standards_rollup: payload.standards_rollup,
      band_high: payload.band_high,
      band_mid: payload.band_mid,
      band_low: payload.band_low,
    };
  }

  const effectiveStrand =
    filters.strand ??
    (filters.standard
      ? pickStrandFromStandard(filters.standard, payload.standards_rollup) ?? null
      : null);

  const matches = (row: { strand: string; schoology_standard?: string }) =>
    (!effectiveStrand || row.strand === effectiveStrand) &&
    (!filters.standard || row.schoology_standard === filters.standard);

  const strandsRollup = payload.strands_rollup.filter(
    (r) => !effectiveStrand || r.strand === effectiveStrand,
  );
  const standardsRollup = payload.standards_rollup.filter(matches);
  const bandHigh = payload.band_high.filter(matches);
  const bandMid = payload.band_mid.filter(matches);
  const bandLow = payload.band_low.filter(matches);

  // KPIs: total_students is immune; rest re-aggregate from filtered rows.
  // Prefer the strand-row aggregates when only a strand is selected (they
  // were computed server-side and carry rounding that the questions-grain
  // recompute would miss); fall back to the standard-row aggregate when
  // a single standard is selected.
  let totalQuestions = payload.kpis.total_questions;
  let totalStandards = payload.kpis.total_standards;
  let gradeAverage = payload.kpis.grade_average;

  if (filters.standard) {
    const single = standardsRollup[0];
    if (single) {
      totalQuestions = single.num_questions;
      totalStandards = 1;
      gradeAverage = single.grade_average;
    }
  } else if (filters.strand) {
    const single = strandsRollup[0];
    if (single) {
      totalQuestions = single.num_questions;
      totalStandards = single.num_standards;
      gradeAverage = single.grade_average;
    }
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

// ─── QRA ─────────────────────────────────────────────────────────────────

interface QraDerived {
  kpis: KPIs;
  questions_overall: QuestionOverall[];
  incorrect_choices: IncorrectChoice[];
  strands_rollup: SddStrandRow[];
  standards_rollup: SddStandardRow[];
}

export function deriveQra(
  payload: QuestionResponseAnalysisPayload,
  filters: ReportFilters,
): QraDerived {
  if (!filters.strand && !filters.standard) {
    return {
      kpis: payload.kpis,
      questions_overall: payload.questions_overall,
      incorrect_choices: payload.incorrect_choices,
      strands_rollup: payload.strands_rollup,
      standards_rollup: payload.standards_rollup,
    };
  }

  const effectiveStrand =
    filters.strand ??
    (filters.standard
      ? pickStrandFromStandard(filters.standard, payload.standards_rollup) ?? null
      : null);

  const strandsRollup = payload.strands_rollup.filter(
    (r) => !effectiveStrand || r.strand === effectiveStrand,
  );
  const standardsRollup = payload.standards_rollup.filter(
    (r) =>
      (!effectiveStrand || r.strand === effectiveStrand) &&
      (!filters.standard || r.schoology_standard === filters.standard),
  );

  // Question rows store all aligned Schoology codes (one per line) in
  // their `standards` field, so we split before matching against the
  // allowed-codes set derived from the (already filtered) rollup.
  const allowedSchoologyCodes = new Set(
    standardsRollup.map((r) => r.schoology_standard).filter(Boolean),
  );

  const questions = payload.questions_overall.filter((q) => {
    const codes = q.standards
      ? q.standards.split('\n').map((s) => s.trim()).filter(Boolean)
      : [];
    return (
      codes.some((c) => allowedSchoologyCodes.has(c)) ||
      allowedSchoologyCodes.has(q.strand)
    );
  });
  const qidSet = new Set(questions.map((q) => q.question_id));
  const incorrectChoices = payload.incorrect_choices.filter((c) =>
    qidSet.has(c.question_id),
  );

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
    total_standards: filters.standard ? 1 : standardsRollup.length,
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
    incorrect_choices: incorrectChoices,
    strands_rollup: strandsRollup,
    standards_rollup: standardsRollup,
  };
}
