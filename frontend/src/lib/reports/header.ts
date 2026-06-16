import type { AssessmentMeta } from './types';

type CourseMeta = Pick<AssessmentMeta, 'subject' | 'grade' | 'item_name'>;

/**
 * The legacy "<Subject> - <Grade>: <Item_Name>" course line shown on every
 * assessment report header, so all report types render the same descriptor.
 *
 * Two display rules (cosmetic only — the underlying dim values are unchanged,
 * filters still show the raw Schoology values):
 *  - Subject is OMITTED when it is the source 'Other'/blank catch-all (Schoology
 *    never assigned a subject), so the header reads "Grade 1: <Item>" instead of
 *    "Other - Grade 1: <Item>".
 *  - A redundant Schoology folder-number prefix on the grade ("1 - Grade 1") is
 *    stripped, mirroring how assessment_type already drops its "N - " prefix, so
 *    we never render "Mathematics - 1 - Grade 1: <Item>".
 */
export function buildAssessmentCourseLine(meta: CourseMeta): string {
  const subject = (meta.subject ?? '').trim();
  const subjectToken =
    !subject || subject.toLowerCase() === 'other' ? '' : subject;
  const grade = (meta.grade ?? '').trim().replace(/^\d+\s*-\s*/, '');
  const left = [subjectToken, grade].filter(Boolean).join(' - ');
  return [left, (meta.item_name ?? '').trim()].filter(Boolean).join(': ');
}

/**
 * ISO date (YYYY-MM-DD) → legacy "M/D/YYYY" with no timezone shift (parsed from
 * the string, not via Date, so the day never drifts). '' when missing.
 */
export function formatAssessmentDate(iso: string | null | undefined): string {
  if (!iso) return '';
  const m = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso);
  if (!m) return '';
  const [, y, mo, d] = m;
  return `${Number(mo)}/${Number(d)}/${y}`;
}
