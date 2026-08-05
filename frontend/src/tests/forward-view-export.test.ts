import { describe, expect, it } from 'vitest';
import { reportToCsv } from '../lib/reports/export-csv';
import type { ForwardViewPayload } from '../lib/reports/types';

const BOM = '﻿';

/** Parse an RFC-4180 CSV (BOM + CRLF) into a matrix of cells. */
function parse(csv: string): string[][] {
  expect(csv.startsWith(BOM)).toBe(true);
  return csv
    .slice(BOM.length)
    .replace(/\r\n$/, '')
    .split('\r\n')
    .map((line) => {
      const cells: string[] = [];
      let cur = '';
      let inQuotes = false;
      for (let i = 0; i < line.length; i += 1) {
        const ch = line[i];
        if (inQuotes) {
          if (ch === '"') {
            if (line[i + 1] === '"') {
              cur += '"';
              i += 1;
            } else {
              inQuotes = false;
            }
          } else {
            cur += ch;
          }
        } else if (ch === '"') {
          inQuotes = true;
        } else if (ch === ',') {
          cells.push(cur);
          cur = '';
        } else {
          cur += ch;
        }
      }
      cells.push(cur);
      return cells;
    });
}

describe('Forward View flattener (one row per period × unit × standard)', () => {
  // 1 period ("Quarter 1"), 2 units. Chapter 1 carries a FLAGGED standard
  // (is_troublesome true, pooled % below the client threshold); Chapter 2
  // carries a NON-flagged standard plus an unassessed (null grade_average)
  // standard to pin the blank "% Correct" contract.
  const payload = {
    periods: [
      {
        period: 'Quarter 1',
        units: [
          {
            unit: 'Chapter 1',
            assessment_date: '2024-11-04',
            flagged_count: 1,
            standards: [
              {
                schoology_standard: 'MA.3.NSO.1.2',
                cpalms_standard: 'M.2.1',
                strand: 'Number Sense',
                description: '<b>Understand</b> place value',
                num_questions: 4,
                total_score: 332,
                total_possible_point: 650,
                grade_average: 0.511,
                grade_average_pct: '51.1%',
                is_troublesome: true,
              },
            ],
          },
          {
            unit: 'Chapter 2',
            assessment_date: '2024-12-01',
            flagged_count: 0,
            standards: [
              {
                schoology_standard: 'MA.3.M.2.1',
                cpalms_standard: 'M.2.1b',
                strand: 'Measurement',
                description: 'Tell time',
                num_questions: 3,
                total_score: 170,
                total_possible_point: 200,
                grade_average: 0.85,
                grade_average_pct: '85.0%',
                is_troublesome: false,
              },
              {
                schoology_standard: 'MA.3.FR.1.1',
                cpalms_standard: 'FR.1.1',
                strand: 'Fractions',
                description: 'Represent fractions',
                num_questions: 0,
                total_score: 0,
                total_possible_point: 0,
                grade_average: null,
                grade_average_pct: '—',
                is_troublesome: false,
              },
            ],
          },
        ],
      },
    ],
  } as unknown as ForwardViewPayload;

  it('emits the exact §2.7 header row', () => {
    const [header] = parse(reportToCsv('forward-view', payload));
    expect(header).toEqual([
      'Period',
      'Unit',
      'Assessment Date',
      'Standard',
      'CPALMS Standard',
      'Strand',
      'Description',
      'Questions',
      'Points Earned',
      'Points Possible',
      '% Correct',
      'Flagged',
    ]);
  });

  it('renders the flagged row verbatim ("Yes"), stripping HTML in Description', () => {
    const rows = parse(reportToCsv('forward-view', payload));
    expect(rows[1]).toEqual([
      'Quarter 1',
      'Chapter 1',
      '2024-11-04',
      'MA.3.NSO.1.2',
      'M.2.1',
      'Number Sense',
      'Understand place value',
      '4',
      '332',
      '650',
      '51.1%',
      'Yes',
    ]);
  });

  it('renders the non-flagged row verbatim ("No")', () => {
    const rows = parse(reportToCsv('forward-view', payload));
    expect(rows[2]).toEqual([
      'Quarter 1',
      'Chapter 2',
      '2024-12-01',
      'MA.3.M.2.1',
      'M.2.1b',
      'Measurement',
      'Tell time',
      '3',
      '170',
      '200',
      '85.0%',
      'No',
    ]);
  });

  it('blanks % Correct for an unassessed (null grade_average) standard', () => {
    const rows = parse(reportToCsv('forward-view', payload));
    // % Correct blank, points zero, Flagged "No" (null can never be flagged).
    expect(rows[3]).toEqual([
      'Quarter 1',
      'Chapter 2',
      '2024-12-01',
      'MA.3.FR.1.1',
      'FR.1.1',
      'Fractions',
      'Represent fractions',
      '0',
      '0',
      '0',
      '',
      'No',
    ]);
  });
});
