import { describe, expect, it } from 'vitest';
import {
  buildAssessmentCourseLine,
  formatAssessmentDate,
} from '../lib/reports/header';

const base = { subject: 'Mathematics', grade: 'Grade 2', item_name: 'Chapter 15 Test: Geometry' };

describe('buildAssessmentCourseLine — shared report-header course line', () => {
  it('renders "<Subject> - <Grade>: <Item>" for a normal subject', () => {
    expect(buildAssessmentCourseLine(base)).toBe(
      'Mathematics - Grade 2: Chapter 15 Test: Geometry',
    );
  });

  it("hides the 'Other' catch-all subject (case-insensitive)", () => {
    expect(
      buildAssessmentCourseLine({ ...base, subject: 'Other' }),
    ).toBe('Grade 2: Chapter 15 Test: Geometry');
    expect(
      buildAssessmentCourseLine({ ...base, subject: 'other' }),
    ).toBe('Grade 2: Chapter 15 Test: Geometry');
  });

  it('hides a blank/whitespace subject', () => {
    expect(buildAssessmentCourseLine({ ...base, subject: '' })).toBe(
      'Grade 2: Chapter 15 Test: Geometry',
    );
    expect(buildAssessmentCourseLine({ ...base, subject: '   ' })).toBe(
      'Grade 2: Chapter 15 Test: Geometry',
    );
  });

  it('strips a redundant Schoology folder-number prefix from the grade', () => {
    expect(
      buildAssessmentCourseLine({ ...base, grade: '2 - Grade 2' }),
    ).toBe('Mathematics - Grade 2: Chapter 15 Test: Geometry');
  });

  it('leaves non-prefixed grades (Higher-Ed) untouched', () => {
    expect(
      buildAssessmentCourseLine({ subject: 'Other', grade: 'Higher-Ed', item_name: 'Topic 10' }),
    ).toBe('Higher-Ed: Topic 10');
  });
});

describe('formatAssessmentDate — legacy M/D/YYYY, no timezone drift', () => {
  it('formats an ISO date without shifting the day', () => {
    expect(formatAssessmentDate('2026-05-21')).toBe('5/21/2026');
    expect(formatAssessmentDate('2026-05-21T00:00:00Z')).toBe('5/21/2026');
    expect(formatAssessmentDate('2026-12-09')).toBe('12/9/2026');
  });

  it('returns "" for null/empty/malformed input', () => {
    expect(formatAssessmentDate(null)).toBe('');
    expect(formatAssessmentDate(undefined)).toBe('');
    expect(formatAssessmentDate('')).toBe('');
    expect(formatAssessmentDate('not-a-date')).toBe('');
  });
});
