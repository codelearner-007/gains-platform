import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import AlignmentEmptyState, {
  variantFor,
} from '@/components/app/modules/reports/shared/AlignmentEmptyState';
import type { AlignmentDataQuality } from '@/lib/reports/types';

// ─── Pure variant copy ──────────────────────────────────────────────────

describe('variantFor', () => {
  it('returns the no-standards-in-source default copy', () => {
    const v = variantFor('no_standards_in_source', 'Standards Deep Dive');
    expect(v.headline).toContain('Standards Deep Dive');
    expect(v.headline).toContain('no standards alignment');
    expect(v.remediation).toContain('Align Learning Objective');
    expect(v.showUnmatched).toBeFalsy();
  });

  it('returns the labels-not-mapped variant with unmatched flag', () => {
    const v = variantFor('labels_not_mapped', 'Question Response Analysis');
    expect(v.headline).toContain("don't match the CPALMS catalog");
    expect(v.remediation).toContain('MA.912.AR.3.1');
    expect(v.showUnmatched).toBe(true);
  });

  it('returns the no-questions variant', () => {
    const v = variantFor('no_questions', 'Strand Summary');
    expect(v.headline).toContain('no questions in the data set');
    expect(v.remediation).toContain('exported correctly from Schoology');
    expect(v.showUnmatched).toBeFalsy();
  });

  it('falls back to default copy when cause is undefined (backward-compat)', () => {
    const v = variantFor(undefined, 'Standard Summary');
    expect(v.headline).toContain('Standard Summary');
    expect(v.headline).toContain('no standards alignment');
    expect(v.showUnmatched).toBeFalsy();
  });

  it('falls back to default copy when cause is null', () => {
    const v = variantFor(null, 'Standard Summary');
    expect(v.headline).toContain('no standards alignment');
    expect(v.showUnmatched).toBeFalsy();
  });

  it('uses the default copy for partial_teacher_alignment and full_alignment', () => {
    expect(variantFor('partial_teacher_alignment', 'X').headline).toContain(
      'no standards alignment',
    );
    expect(variantFor('full_alignment', 'X').headline).toContain(
      'no standards alignment',
    );
  });
});

// ─── Rendered component (static markup) ─────────────────────────────────

function baseQuality(
  overrides: Partial<AlignmentDataQuality> = {},
): AlignmentDataQuality {
  return {
    alignment_status: 'missing',
    questions_total: 12,
    questions_with_alignment: 0,
    items_total: 1,
    items_with_alignment: 0,
    remediation_hint:
      'Open this assessment in Schoology and align each question to a CPALMS standard.',
    ...overrides,
  };
}

describe('<AlignmentEmptyState />', () => {
  it('renders the no_standards_in_source variant when cause is set', () => {
    const html = renderToStaticMarkup(
      createElement(AlignmentEmptyState, {
        quality: baseQuality({ cause: 'no_standards_in_source' }),
        reportLabel: 'Standards Deep Dive',
      }),
    );
    expect(html).toContain('Standards Deep Dive');
    expect(html).toContain('no standards alignment');
    expect(html).toContain('Align Learning Objective');
    expect(html).not.toContain('Unrecognized labels');
  });

  it('renders the labels_not_mapped variant with the unmatched_labels list', () => {
    const html = renderToStaticMarkup(
      createElement(AlignmentEmptyState, {
        quality: baseQuality({
          cause: 'labels_not_mapped',
          unmatched_labels: ['Social Studies', 'Reading Comprehension'],
        }),
        reportLabel: 'Question Response Analysis',
      }),
    );
    expect(html).toContain("don&#x27;t match the CPALMS catalog");
    expect(html).toContain('Unrecognized labels in this assessment:');
    expect(html).toContain('Social Studies');
    expect(html).toContain('Reading Comprehension');
    expect(html).toContain('MA.912.AR.3.1');
  });

  it('caps the unmatched_labels list at 5 items', () => {
    const labels = ['A', 'B', 'C', 'D', 'E', 'F', 'G'];
    const html = renderToStaticMarkup(
      createElement(AlignmentEmptyState, {
        quality: baseQuality({
          cause: 'labels_not_mapped',
          unmatched_labels: labels,
        }),
        reportLabel: 'Strand Summary',
      }),
    );
    expect(html).toContain('>A<');
    expect(html).toContain('>E<');
    expect(html).not.toContain('>F<');
    expect(html).not.toContain('>G<');
  });

  it('hides the unmatched list when labels_not_mapped has empty unmatched_labels', () => {
    const html = renderToStaticMarkup(
      createElement(AlignmentEmptyState, {
        quality: baseQuality({
          cause: 'labels_not_mapped',
          unmatched_labels: [],
        }),
        reportLabel: 'X',
      }),
    );
    expect(html).not.toContain('Unrecognized labels');
  });

  it('falls back to the legacy generic copy + remediation_hint when cause is undefined (backward-compat)', () => {
    const html = renderToStaticMarkup(
      createElement(AlignmentEmptyState, {
        quality: baseQuality(),
        reportLabel: 'Standards Deep Dive',
      }),
    );
    expect(html).toContain('Standards Deep Dive');
    expect(html).toContain('no standards alignment');
    // legacy path renders the backend-supplied remediation_hint verbatim
    expect(html).toContain(
      'Open this assessment in Schoology and align each question to a CPALMS standard.',
    );
    // legacy path does NOT include the new explanatory body paragraph
    expect(html).not.toContain('does not include any aligned learning objectives');
    expect(html).not.toContain('Unrecognized labels');
  });

  it('renders the aggregate-scope headline when items_total > 1 and no cause', () => {
    const html = renderToStaticMarkup(
      createElement(AlignmentEmptyState, {
        quality: baseQuality({ items_total: 12, items_with_alignment: 0 }),
        reportLabel: 'Standard Summary',
      }),
    );
    expect(html).toContain('no questions in scope are aligned to standards');
    expect(html).toContain('Assessments in scope');
  });

  it('always shows the questions-in-scope stat line', () => {
    const html = renderToStaticMarkup(
      createElement(AlignmentEmptyState, {
        quality: baseQuality({
          cause: 'no_standards_in_source',
          questions_total: 10,
          questions_with_alignment: 0,
        }),
        reportLabel: 'X',
      }),
    );
    expect(html).toContain('Questions in scope');
    expect(html).toContain('0 of 10 aligned');
  });
});
