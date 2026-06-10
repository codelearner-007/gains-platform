// PBIX-mandated traffic-light thresholds. Do NOT replace with semantic tokens.
// Source: data/_pbix_extract/04_dax_measures.dax (Performance Color* measures)
// and data/_pbix_extract/30_qra_interactive.json (per-visual conditional formatting).
//
// PBIX uses #ff2800 / #faff00 / #00ff06 (intense red / bright yellow / vivid
// green). The platform softens the low band to a pink users called out as the
// preferred semantic colour ("pink = needs improvement"), keeps yellow for
// 70–80% and uses the same vivid green for ≥80%. Three-band semantics are
// preserved across every report (QRA cells, SDD/Strand treemaps, summary
// chips), so a viewer can read traffic-light meaning at a glance.

export const PERF_PINK = '#FFB3D9'; // legible on white, still reads as pink
export const PERF_YELLOW = '#FFF066'; // less harsh than pure yellow at large sizes
export const PERF_GREEN = '#7BE38C'; // softer green for chart fills + chips

// ── IAD per-student saturated palette ───────────────────────────────────────
// PBIX page #19 (IAD) explicitly uses brighter saturated colors on the
// Per-Student Attempts table cell fills — distinct from the QRA / SDD pastel
// palette so the per-student grid reads clearly at small sizes. Hexes are
// verbatim from `_layout.full.json` IAD visual #10 `objects.values[0]
// .properties.backColor.Conditional.Cases`.
export const IAD_RED = '#ff2800'; // wrong cell fill (Points_Received = '0')
export const IAD_GREEN = '#00ff44'; // correct cell fill

// ── Layout / chrome colors (PBIX-mandated, shared across reports) ───────────
// Centralized here so all report views (QRA, SDD, YTD, IAD, Standard
// Summary, Strand Summary) stay visually consistent and we never
// grep-replace inline hex literals across components.
export const KPI_CARD_BG = '#B8DBFF'; // PBIX-style KPI tile background
export const HEADER_BAR_BG = '#B8DBFF'; // section header bars (same hue, different role)
export const LAYOUT_BORDER = '#B3B3B3'; // standard report border
export const INCORRECT_GREY = '#CCCCCC'; // grey fill used in incorrect-bar series
export const GRID_LINE = '#E5E5E5'; // table grid lines / cell borders

// ── Paginated reports (PBIX ord 6/7/16, 11, 12, 13) ─────────────────────────
// Tokens used by the column-group headers, secondary header rows, and group
// header bands in the new paginated table family. Match the Office accent
// palette as rendered in the legacy SSRS PDFs.
export const PBIX_ACCENT_NAVY = '#4472C4'; // Standard / outer column-group header
export const PBIX_ACCENT_LIGHT_BLUE = '#8FAADC'; // Question-No / inner header row
export const GROUP_HEADER_CYAN = '#D6F1EF'; // Teacher / Standard group band

// ── Question Summary Report (QSR) exact legacy fills ────────────────────────
// Verbatim from the rendered legacy SSRS PDFs (e.g. "Unit 6 Test- Heat Sources
// …-Question Summary Report - color.pdf"). The QSR uses BRIGHTER fills than the
// softened PERF_* report tokens above — keep both: PERF_* drives the
// interactive QRA/SDD/summary surfaces, QSR_* drives this paginated family so
// it is pixel-faithful to the legacy print output. Do NOT collapse the two.
//   correct cell / Score% ≥80%   → #99FF99 (green)
//   incorrect cell / Score% <70% → #FFCCFF (pink)
//   Score% 70–80%                → #FFF591 (yellow)
export const QSR_GREEN = '#99FF99';
export const QSR_PINK = '#FFCCFF';
export const QSR_YELLOW = '#FFF591';

/** Three-band Score% fill for the QSR family (exact legacy hexes). */
export function qsrPerformanceColor(grade: number): string {
  if (grade < 0.7) return QSR_PINK;
  if (grade < 0.8) return QSR_YELLOW;
  return QSR_GREEN;
}

/**
 * Partial-credit QSR leaf-cell fill. A cell carries `points_received` (may be
 * fractional); the legacy SSRS / xlsx colors it green at >=0.5 received, pink
 * below (matches `_qsr_cell_fill` in report_export_service.py). `null`
 * (not attempted) gets no fill. Two-band ONLY — distinct from the three-band
 * Score% fill above; do NOT collapse the two.
 */
export function qsrCellColor(received: number | null): string | undefined {
  if (received === null) return undefined;
  return received >= 0.5 ? QSR_GREEN : QSR_PINK;
}

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

// Cell-background colour for grade-coloured percentage cells (QRA per-question
// table, strands / standards summary tables). Mirrors PBIX semantics so the
// pink/yellow/green traffic light is consistent across every report.
export const cellColor = performanceColor;

export function performanceTextColor(): string {
  return '#000000';
}
