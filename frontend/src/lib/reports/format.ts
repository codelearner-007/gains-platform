// Replicates DAX `FormattedString` (cube_question_summary_overall):
// `<` -> `<img width='30%' src='`, `>` -> `' />`, but only when the angle
// brackets enclose a URL.
//
// Security: any other HTML (including <script>, <img onerror=...>, javascript:
// URIs, etc.) is stripped/sanitized via sanitize-html. The captured URL is
// also HTML-escaped before being interpolated into the src attribute so a URL
// containing `"` cannot break out of the attribute.
//
// Why sanitize-html (not isomorphic-dompurify): the latter loads jsdom on the
// server, and jsdom's transitive `@exodus/bytes` ships ESM-only while
// `html-encoding-sniffer` still uses `require()`, so SSR errors with
// ERR_REQUIRE_ESM and Next.js falls back to client rendering. sanitize-html
// is a native Node implementation with no jsdom dependency.
import sanitizeHtml from 'sanitize-html';

const URL_IN_BRACKETS = /<(https?:\/\/[^>\s]+)>/g;

function escapeHtml(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

function decodeRepeatedly(value: string): string {
  let current = value;
  for (let i = 0; i < 3; i += 1) {
    try {
      const decoded = decodeURIComponent(current);
      if (decoded === current) break;
      current = decoded;
    } catch {
      break;
    }
  }
  return current;
}

function escapeSvgText(s: string): string {
  return s
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;');
}

function latexToReadableText(latex: string): string {
  return latex
    .replace(/\\small\s*/g, '')
    .replace(/\\left|\\right/g, '')
    .replace(/\\ne/g, '≠')
    .replace(/\\times/g, '×')
    .replace(/\\cdot/g, '·')
    .replace(/\\pm/g, '±')
    .replace(/\\leq?/g, '≤')
    .replace(/\\geq?/g, '≥')
    .replace(/\s+/g, ' ')
    .trim();
}

function latexSvgDataUri(latex: string): string {
  const text = latexToReadableText(latex) || latex;
  const width = Math.max(40, Math.min(520, text.length * 8 + 18));
  const svg = `<svg xmlns="http://www.w3.org/2000/svg" width="${width}" height="28" viewBox="0 0 ${width} 28"><rect width="100%" height="100%" fill="white" fill-opacity="0"/><text x="2" y="19" font-family="Cambria Math, Times New Roman, serif" font-size="17" fill="black">${escapeSvgText(text)}</text></svg>`;
  return `data:image/svg+xml;charset=utf-8,${encodeURIComponent(svg)}`;
}

function extractSchoologyLatex(raw: string): string | null {
  const variants = [raw];
  let current = raw;
  for (let i = 0; i < 3; i += 1) {
    try {
      current = decodeURIComponent(current);
      variants.push(current);
    } catch {
      break;
    }
  }

  for (const variant of variants) {
    if (!variant.includes('latex-to-svg')) continue;
    const match = variant.match(/[?&]latex=([^&#]+)/);
    if (!match) continue;
    return decodeRepeatedly(match[1].replace(/\+/g, ' '));
  }
  return null;
}

/**
 * Schoology's CSV export can wrap asset URLs in PowerBI-era proxy paths like:
 *   https://app.schoology.com/system/files/%252Fsystem/files/attachments/...
 *   https://app.schoology.com/system/files/https%3A/%252Faaota.schoology.com/system/files/...
 * Those URLs return 404 in a normal browser. Normalize them back to the public
 * `/system/files/attachments/...` asset URL so the browser can follow
 * Schoology's signed CDN redirect and render the image.
 */
export function normalizeSchoologyAssetUrl(raw: string): string {
  if (!raw) return '';
  const trimmed = raw.trim();
  let parsed: URL;
  try {
    parsed = new URL(trimmed);
  } catch {
    return trimmed;
  }

  const host = parsed.hostname.toLowerCase();
  if (!host.endsWith('schoology.com')) return trimmed;

  const latex = extractSchoologyLatex(trimmed);
  if (latex) return latexSvgDataUri(latex);

  const decoded = decodeRepeatedly(trimmed);

  const nestedUrl = decoded.match(
    /^https?:\/\/[^/]+\/system\/files\/(https?:\/\/[^\s]+)$/,
  );
  if (nestedUrl) {
    try {
      return new URL(nestedUrl[1]).toString();
    } catch {
      return nestedUrl[1];
    }
  }

  const doubleSystemFiles = decoded.match(
    /^(https?:\/\/[^/]+)\/system\/files\/+system\/files\/(.+)$/,
  );
  if (doubleSystemFiles) {
    return `${doubleSystemFiles[1]}/system/files/${doubleSystemFiles[2]}`;
  }

  return trimmed;
}

function renderImageTag(url: string, alt: string): string {
  const normalizedUrl = normalizeSchoologyAssetUrl(url);
  const className = normalizedUrl.startsWith('data:image/svg+xml')
    ? 'report-rich-image report-latex-image'
    : 'report-rich-image';
  return `<img class="${className}" src="${escapeHtml(
    normalizedUrl,
  )}" alt="${escapeHtml(alt)}" decoding="async" referrerpolicy="no-referrer" />`;
}

function renderUrlTokens(raw: string, alt: string): string {
  const withBracketedUrls = raw.replace(URL_IN_BRACKETS, (_m, url) =>
    renderImageTag(url, alt),
  );
  return withBracketedUrls.replace(
    /(^|[\s([])(https?:\/\/[^\s<>"')\]]+)/g,
    (_m, prefix, url) => `${prefix}${renderImageTag(url, alt)}`,
  );
}

const QUESTION_TAGS = ['img', 'br', 'p', 'strong', 'em', 'b', 'i', 'span'];
const ANSWER_TAGS = ['img', 'br', 'span'];
const ALLOWED_ATTR_LIST = [
  'src',
  'alt',
  'width',
  'height',
  'class',
  'decoding',
  'referrerpolicy',
];

function sanitizeFor(tags: string[], html: string): string {
  return sanitizeHtml(html, {
    allowedTags: tags,
    allowedAttributes: { '*': ALLOWED_ATTR_LIST },
    allowedSchemes: ['http', 'https', 'data'],
    allowedSchemesByTag: { img: ['http', 'https', 'data'] },
  });
}

export function formatQuestionHtml(raw: string): string {
  if (!raw) return '';
  const replaced = renderUrlTokens(raw, 'question');
  return sanitizeFor(QUESTION_TAGS, replaced.trim());
}

export function formatAnswerHtml(raw: string, alt = 'answer'): string {
  if (!raw) return '';
  const replaced = renderUrlTokens(raw, alt);
  return sanitizeFor(
    ANSWER_TAGS,
    replaced.trim().replace(/\n/g, '<br />'),
  );
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

export function formatNumber(value: number): string {
  if (!Number.isFinite(value)) return '';
  // Drop trailing .0 when integer-valued; otherwise keep 1-2 decimals.
  return Number.isInteger(value)
    ? value.toLocaleString('en-US')
    : value.toLocaleString('en-US', { maximumFractionDigits: 2 });
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
// Kept for compact text-only contexts (charts/axes/export labels). QRA table
// cells now use `formatAnswerHtml` so image answers render as thumbnails.

const SHORT_ANSWER_URL_IN_BRACKETS = /<https?:\/\/[^>\s]+>/g;
const SHORT_ANSWER_BARE_URL = /^https?:\/\/[^\s]+$/;

/**
 * Normalise a short answer label for inline text display:
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

export function splitStandards(raw: string | null | undefined): string[] {
  if (!raw) return [];
  return raw.split('\n').map((s) => s.trim()).filter(Boolean);
}
