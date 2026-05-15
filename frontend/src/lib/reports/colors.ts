// PBIX-mandated traffic-light thresholds. Do NOT replace with semantic tokens.
// Source: data/_pbix_extract/04_dax_measures.dax (Performance Color* measures)
// and data/_pbix_extract/30_qra_interactive.json (per-visual conditional formatting).

export const PERF_PINK = '#FFCCFF';
export const PERF_YELLOW = 'yellow';
export const PERF_GREEN = '#00FF06';

// ── Layout / chrome colors (PBIX-mandated, shared across reports) ───────────
// Centralized here so all report views (QRA, SDD, YTD, IAD, Standard
// Summary, Strand Summary) stay visually consistent and we never
// grep-replace inline hex literals across components.
export const KPI_CARD_BG = '#B8DBFF'; // PBIX-style KPI tile background
export const HEADER_BAR_BG = '#B8DBFF'; // section header bars (same hue, different role)
export const LAYOUT_BORDER = '#B3B3B3'; // standard report border
export const INCORRECT_GREY = '#CCCCCC'; // grey fill used in incorrect-bar series
export const GRID_LINE = '#E5E5E5'; // table grid lines / cell borders

// ── Status icon hexes (used inside cells for the Check / X marks) ───────────
// Tailwind `green-700` and `red-700` from the project palette, hard-coded so
// the icons stay legible on the green/pink traffic-light cell backgrounds.
export const STATUS_CORRECT_FG = '#15803d';
export const STATUS_INCORRECT_FG = '#b91c1c';
export const EMPTY_TABLE_FG = '#6b7280';

// ── Standard Summary card chrome (mirrors PBIX page #14 spec §8) ────────────
export const STANDARD_HEADER_BG = '#0E1A77'; // deep navy card header
export const STANDARD_HEADER_FG = '#FFFFFF';
export const STRAND_CHIP_BG = '#E0E7FF';
export const STRAND_CHIP_FG = '#1E1B4B';
export const NEUTRAL_CHIP_BG = '#F3F4F6';
export const NEUTRAL_CHIP_FG = '#111827';
// Cognitive-complexity chips (low / mid / high contrast tones).
export const COMPLEXITY_HIGH_BG = '#FECACA';
export const COMPLEXITY_HIGH_FG = '#7F1D1D';
export const COMPLEXITY_MID_BG = '#FEF3C7';
export const COMPLEXITY_MID_FG = '#78350F';
export const COMPLEXITY_LOW_BG = '#DCFCE7';
export const COMPLEXITY_LOW_FG = '#14532D';
export const COMPLEXITY_DEFAULT_BG = '#E5E5E5';
export const COMPLEXITY_DEFAULT_FG = '#000000';

export function performanceColor(grade: number): string {
  if (grade < 0.7) return PERF_PINK;
  if (grade < 0.8) return PERF_YELLOW;
  return PERF_GREEN;
}

// For the "Question Response Analysis" simple page, low-score cells stay white
// (no pink fill). Used for the per-question table cell #3 and the strands /
// standards summary tables.
export function cellColor(grade: number): string {
  if (grade < 0.7) return 'transparent';
  if (grade < 0.8) return PERF_YELLOW;
  return PERF_GREEN;
}

export function performanceTextColor(): string {
  return '#000000';
}
