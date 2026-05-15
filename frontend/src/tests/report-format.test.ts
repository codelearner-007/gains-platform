import { describe, expect, it } from 'vitest';
import {
  deriveAssessmentLabel,
  sanitizeShortAnswer,
} from '../lib/reports/format';

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
