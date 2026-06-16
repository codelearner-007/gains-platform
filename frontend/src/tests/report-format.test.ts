import { describe, expect, it } from 'vitest';
import {
  deriveAssessmentLabel,
  formatAnswerHtml,
  formatQuestionHtml,
  normalizeSchoologyAssetUrl,
  sanitizeShortAnswer,
} from '../lib/reports/format';

describe('Schoology image URL rendering', () => {
  it('normalizes double-encoded /system/files wrappers', () => {
    expect(
      normalizeSchoologyAssetUrl(
        'https://app.schoology.com/system/files/%252Fsystem/files/attachments/page_embeds/m/2023-03/Screenshot.png',
      ),
    ).toBe(
      'https://app.schoology.com/system/files/attachments/page_embeds/m/2023-03/Screenshot.png',
    );
  });

  it('normalizes nested host wrappers', () => {
    expect(
      normalizeSchoologyAssetUrl(
        'https://app.schoology.com/system/files/https%3A/%252Faaota.schoology.com/system/files/attachments/page_embeds/m/2023-04/Screenshot.png',
      ),
    ).toBe(
      'https://aaota.schoology.com/system/files/attachments/page_embeds/m/2023-04/Screenshot.png',
    );
  });

  it('upgrades http:// asset URLs to https:// (mixed-content fix)', () => {
    // ~13k stored URLs are pre-2023 http:// exports; on the https prod site
    // they are mixed content. The asset is always served over https.
    expect(
      normalizeSchoologyAssetUrl(
        'http://app.schoology.com/system/files/http%3A/%252Fapp.schoology.com/system/files/attachments/page_embeds/m/2022-07/614040.gif',
      ),
    ).toBe(
      'https://app.schoology.com/system/files/attachments/page_embeds/m/2022-07/614040.gif',
    );
  });

  it('upgrades a plain http:// asset URL with no wrapper', () => {
    expect(
      normalizeSchoologyAssetUrl(
        'http://app.schoology.com/system/files/attachments/page_embeds/m/2022-07/x.png',
      ),
    ).toBe(
      'https://app.schoology.com/system/files/attachments/page_embeds/m/2022-07/x.png',
    );
  });

  it('renders question stems as image tags with normalized URLs', () => {
    const html = formatQuestionHtml(
      '<https://app.schoology.com/system/files/%252Fsystem/files/attachments/page_embeds/m/2023-03/Screenshot.png>',
    );
    expect(html).toContain(
      'src="https://app.schoology.com/system/files/attachments/page_embeds/m/2023-03/Screenshot.png"',
    );
    expect(html).toContain('class="report-rich-image"');
    expect(html).toContain('decoding="async"');
    expect(html).toContain('referrerpolicy="no-referrer"');
    expect(html).not.toContain('loading="lazy"');
  });

  it('renders image answers as thumbnail image tags', () => {
    expect(
      formatAnswerHtml(
        'b. <https://app.schoology.com/system/files/%252Fsystem/files/attachments/page_embeds/m/2023-03/Answer.png>',
      ),
    ).toContain('alt="answer"');
    expect(
      formatAnswerHtml(
        'b. <https://app.schoology.com/system/files/%252Fsystem/files/attachments/page_embeds/m/2023-03/Answer.png>',
      ),
    ).toContain('/system/files/attachments/page_embeds/m/2023-03/Answer.png');
  });

  it('renders bare image URLs in answers so exported report text does not show raw links', () => {
    const html = formatAnswerHtml(
      'b. https://app.schoology.com/system/files/%252Fsystem/files/attachments/page_embeds/m/2023-03/Answer.png',
    );
    expect(html).toContain('b. <img');
    expect(html).toContain('/system/files/attachments/page_embeds/m/2023-03/Answer.png');
    expect(html).not.toContain('%252Fsystem/files');
  });

  it('converts inaccessible Schoology latex image URLs to local SVG data URIs', () => {
    const normalized = normalizeSchoologyAssetUrl(
      'https://app.schoology.com/system/files/https%3A/%252Faaota.schoology.com/svc/latex/latex-to-svg%3Flatex%3D%255Csmall%252027%253D-5x%255Cleft%280.2x-2%255Cright%29%252B3',
    );
    expect(normalized).toContain('data:image/svg+xml');
    expect(decodeURIComponent(normalized)).toContain('27=-5x(0.2x-2)+3');
  });
});

describe('sanitizeShortAnswer', () => {
  it('returns "" for empty/nullish input', () => {
    expect(sanitizeShortAnswer(null)).toBe('');
    expect(sanitizeShortAnswer(undefined)).toBe('');
    expect(sanitizeShortAnswer('')).toBe('');
    expect(sanitizeShortAnswer('   ')).toBe('');
  });

  it('replaces a bare URL with [image]', () => {
    expect(
      sanitizeShortAnswer('https://app.schoology.com/system/files/image.png'),
    ).toBe('[image]');
  });

  it('replaces a single bracketed URL while preserving prefix', () => {
    expect(
      sanitizeShortAnswer(
        'c. <https://app.schoology.com/system/files/image.png>',
      ),
    ).toBe('c. [image]');
  });

  it('replaces every bracketed URL in mixed-content strings', () => {
    const raw =
      '12.5% chose [a. <https://app.schoology.com/x.png>], 7.4% chose [b. <https://app.schoology.com/y.png>]';
    expect(sanitizeShortAnswer(raw)).toBe(
      '12.5% chose [a. [image]], 7.4% chose [b. [image]]',
    );
  });

  it('leaves plain text untouched', () => {
    expect(sanitizeShortAnswer('42')).toBe('42');
    expect(sanitizeShortAnswer('  Hello world  ')).toBe('Hello world');
  });

  it('does not double-replace already-sanitised input', () => {
    expect(sanitizeShortAnswer('c. [image]')).toBe('c. [image]');
  });
});

describe('deriveAssessmentLabel', () => {
  it('strips leading "<digits> - " prefix', () => {
    expect(deriveAssessmentLabel('1 - Lesson Assessments')).toBe(
      'Lesson Assessments',
    );
    expect(deriveAssessmentLabel('  42 - Mock Test  ')).toBe('Mock Test');
  });

  it('collapses repeated whitespace from upstream data', () => {
    expect(deriveAssessmentLabel('Lesson  Assessments')).toBe(
      'Lesson Assessments',
    );
  });

  it('returns trimmed input when no prefix is present', () => {
    expect(deriveAssessmentLabel('  Other  ')).toBe('Other');
  });
});
