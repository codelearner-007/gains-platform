// Replicates DAX `FormattedString` (cube_question_summary_overall):
// `<` -> `<img width='30%' src='`, `>` -> `' />`, but only when the angle
// brackets enclose a URL.
//
// Security: any other HTML (including <script>, <img onerror=...>, javascript:
// URIs, etc.) is stripped/sanitized via DOMPurify. The captured URL is also
// HTML-escaped before being interpolated into the src attribute so a URL
// containing `"` cannot break out of the attribute.
import DOMPurify from 'isomorphic-dompurify';

const URL_IN_BRACKETS = /<(https?:\/\/[^>\s]+)>/g;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

export function formatQuestionHtml(raw: string): string {
  if (!raw) return '';
  const replaced = raw.replace(
    URL_IN_BRACKETS,
    (_m, url) =>
      `<img width="30%" src="${escapeHtml(url)}" alt="question" />`,
  );
  return DOMPurify.sanitize(replaced.trim(), {
    ALLOWED_TAGS: ['img', 'br', 'p', 'strong', 'em', 'b', 'i', 'span'],
    ALLOWED_ATTR: ['src', 'alt', 'width', 'height'],
  });
}

// Multi-line correct-answer formatter. Rebuilds tokens from comma-joined string.
export function formatCorrectAnswer(raw: string): string[] {
  if (!raw) return [];
  if (!raw.includes(',')) return [raw.trim()];
  const tokens = raw.split(',').map((t) => t.trim()).filter(Boolean);
  return tokens.length > 0 ? tokens : [raw];
}

export function formatPercent(value: number, digits = 1): string {
  if (!Number.isFinite(value)) return '';
  return `${(value * 100).toFixed(digits)}%`;
}

// ── Shared report constants / string helpers ───────────────────────────────

/** Local fallback logo used when an assessment / school has no `logo_url`. */
export const FALLBACK_LOGO = '/pilot/athenian-logo.png';

/**
 * Strip the leading "<digits> - " prefix and collapse whitespace from an
 * `assessment_type` label so it renders cleanly in report headers.
 */
export function deriveAssessmentLabel(raw: string): string {
  return raw
    .replace(/^\s*\d+\s*-\s*/, '')
    .replace(/\s{2,}/g, ' ')
    .trim();
}

// ── Schoology image-answer placeholder ─────────────────────────────────────
// Schoology answer choices for image-based questions arrive as text like
//   "c. <https://app.schoology.com/system/files/.../page_embeds/m/2023-03-15/Screenshot.png>"
// The QRA question summary table, IAD distractor table / chart axis, and the
// IAD per-student attempts table display these short labels inline (not as
// rendered HTML), so they leak the raw URL into the UI. `formatQuestionHtml`
// already handles the *question stem* path by converting to <img>; this helper
// covers the inline-label path by replacing each URL with "[image]" while
// preserving the leading letter prefix when present.

const SHORT_ANSWER_URL_IN_BRACKETS = /<https?:\/\/[^>\s]+>/g;
const SHORT_ANSWER_BARE_URL = /^https?:\/\/[^\s]+$/;

/**
 * Normalise a short answer label for inline display:
 *   - "c. <https://…>"            → "c. [image]"
 *   - "https://…"                 → "[image]"
 *   - "[a. <https://…>]"          → "[a. [image]]"
 *   - everything else             → trimmed, unchanged
 *
 * Returns "" when the input is empty/null. Always returns a string (never
 * HTML); safe to render as text. Multiple URLs in the same string are each
 * replaced with `[image]`.
 */
export function sanitizeShortAnswer(raw: string | null | undefined): string {
  if (!raw) return '';
  const trimmed = String(raw).trim();
  if (!trimmed) return '';
  if (SHORT_ANSWER_BARE_URL.test(trimmed)) return '[image]';
  return trimmed.replace(SHORT_ANSWER_URL_IN_BRACKETS, '[image]');
}
