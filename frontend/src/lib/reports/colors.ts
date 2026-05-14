// PBIX-mandated traffic-light thresholds. Do NOT replace with semantic tokens.
// Source: data/_pbix_extract/04_dax_measures.dax (Performance Color* measures)
// and data/_pbix_extract/30_qra_interactive.json (per-visual conditional formatting).

export const PERF_PINK = '#FFCCFF';
export const PERF_YELLOW = 'yellow';
export const PERF_GREEN = '#00FF06';

// ── Layout / chrome colors (PBIX-mandated, shared across reports) ───────────
// Centralized here so the three report views (QRA, SDD, YTD) stay visually
// consistent and we never grep-replace inline hex literals across components.
export const KPI_CARD_BG = '#B8DBFF'; // PBIX-style KPI tile background
export const HEADER_BAR_BG = '#B8DBFF'; // section header bars (same hue, different role)
export const LAYOUT_BORDER = '#B3B3B3'; // standard report border
export const INCORRECT_GREY = '#CCCCCC'; // grey fill used in incorrect-bar series
export const GRID_LINE = '#E5E5E5'; // table grid lines / cell borders

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
