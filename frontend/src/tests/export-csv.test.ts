import { describe, expect, it } from 'vitest';
import {
  buildCsvFilename,
  reportToCsv,
  rowsToCsv,
  sanitizeFilenameSegment,
} from '../lib/reports/export-csv';
import type {
  IncorrectAnswerDetailsPayload,
  QraByStandardTeacherPayload,
  QraByTeacherPayload,
  QraPaginatedPayload,
  QuestionResponseAnalysisPayload,
  QuestionSummaryMatrixPayload,
  StandardSummaryPayload,
  StandardsDeepDivePayload,
  StrandSummaryPayload,
  YearToDatePerformancePayload,
} from '../lib/reports/types';

const BOM = '﻿';

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

describe('rowsToCsv (RFC-4180)', () => {
  it('prefixes UTF-8 BOM and uses CRLF line endings', () => {
    const csv = rowsToCsv([['a', 'b'], ['c', 'd']]);
    expect(csv.startsWith(BOM)).toBe(true);
    expect(csv).toContain('\r\n');
    expect(csv.endsWith('\r\n')).toBe(true);
  });

  it('quotes fields with comma, quote, or newline and escapes quotes', () => {
    const csv = rowsToCsv([['plain', 'a,b', 'has "q"', 'line\nbreak']]);
    const [row] = parse(csv);
    expect(row).toEqual(['plain', 'a,b', 'has "q"', 'line\nbreak']);
    // The raw line must wrap the special fields in quotes.
    const rawLine = csv.slice(BOM.length).replace(/\r\n$/, '');
    expect(rawLine).toContain('"a,b"');
    expect(rawLine).toContain('"has ""q"""');
  });

  it('renders null/undefined as empty cells', () => {
    const [row] = parse(rowsToCsv([['x', null, undefined, 0]]));
    expect(row).toEqual(['x', '', '', '0']);
  });
});

describe('sanitizeFilenameSegment + buildCsvFilename', () => {
  it('strips unsafe chars and collapses dashes', () => {
    expect(sanitizeFilenameSegment('Unit 6 Test: Heat/Sources!')).toBe(
      'Unit-6-Test-Heat-Sources',
    );
  });

  it('falls back to "report" for empty segments', () => {
    expect(sanitizeFilenameSegment('!!!')).toBe('report');
  });

  it('builds <report>-<name>-<YYYYMMDD>.csv', () => {
    const name = buildCsvFilename('qra', 'Unit 6 Test', new Date(2026, 5, 9));
    expect(name).toBe('qra-Unit-6-Test-20260609.csv');
  });
});

describe('QRA flattener (one row per question)', () => {
  const payload = {
    questions_overall: [
      {
        question_id: 'q1',
        question_no: '1',
        question: '<p>What is 2+2? <img src="http://x/y.png" /></p>',
        correct_answer: 'b. <https://img/c.png>',
        grade_average: 0.5,
        percentage_incorrect: 0.5,
        incorrect_choice_details: '50.0% chose [a. wrong]',
        incorrect_details_name: 'Alice, Bob',
        standards: 'MA.912.AR.3.1\nMA.912.AR.3.2',
      },
      {
        question_id: 'q2',
        question_no: '2',
        question: 'Perfect question',
        correct_answer: 'a',
        grade_average: 1,
        percentage_incorrect: 0,
        incorrect_choice_details: 'should be hidden',
        incorrect_details_name: 'should be hidden',
        standards: 'MA.912.AR.4.1',
      },
    ],
  } as unknown as QuestionResponseAnalysisPayload;

  it('flattens visible question grain with stripped HTML and joined standards', () => {
    const rows = parse(reportToCsv('qra', payload));
    expect(rows[0]).toEqual([
      'Question No',
      'Question',
      'Standards',
      'Correct Answer',
      'Grade Average %',
      '% Incorrect',
      'Incorrect Choices',
      'Incorrect Choice Students',
    ]);
    // Row 1: HTML tags stripped, inline <img> dropped (images are not kept),
    // standards joined with "; ". A bracketed image URL in a text answer cell
    // collapses to [image] via sanitizeShortAnswer (see correct_answer below).
    expect(rows[1][1]).toBe('What is 2+2?');
    expect(rows[1][2]).toBe('MA.912.AR.3.1; MA.912.AR.3.2');
    expect(rows[1][3]).toBe('b. [image]');
    expect(rows[1][4]).toBe('50.0%');
    expect(rows[1][5]).toBe('50.0%');
    expect(rows[1][6]).toBe('50.0% chose [a. wrong]');
    expect(rows[1][7]).toBe('Alice, Bob');
  });

  it('blanks incorrect-choice columns when the question was fully correct', () => {
    const rows = parse(reportToCsv('qra', payload));
    expect(rows[2][4]).toBe('100.0%');
    expect(rows[2][6]).toBe('');
    expect(rows[2][7]).toBe('');
  });
});

describe('QRA-paginated flattener', () => {
  const payload = {
    questions: [
      {
        question_id: 'q1',
        question_no: '1',
        sorting_question_no: 1,
        position_number: '1',
        question: 'Q1',
        correct_answer: 'a',
        grade_average: 0.75,
        grade_average_pct: '75.0%',
        incorrect_choice_details: '25% chose [b]',
        incorrect_details_name: 'Carol',
        standards: 'MA.1',
        cpalms_standard: 'MA.1',
      },
    ],
  } as unknown as QraPaginatedPayload;

  it('produces the same question grain as interactive QRA', () => {
    const rows = parse(reportToCsv('qra-paginated', payload));
    expect(rows).toHaveLength(2);
    expect(rows[1][0]).toBe('1');
    expect(rows[1][4]).toBe('75.0%');
    expect(rows[1][7]).toBe('Carol');
  });
});

describe('QRA-by-teacher flattener (group header + members)', () => {
  const payload = {
    teacher_groups: [
      {
        section_instructor: 'Ms. Lee',
        teacher_grade_average: 0.8,
        teacher_grade_average_pct: '80.0%',
        questions: [
          {
            question_id: 'q1',
            question_no: '1',
            sorting_question_no: 1,
            position_number: '1',
            question: 'Q1',
            correct_answer: 'a',
            grade_average: 0.9,
            grade_average_pct: '90.0%',
            incorrect_choice_details: '',
            incorrect_details_name: '',
            standards: 'MA.1',
            cpalms_standard: 'MA.1',
          },
        ],
      },
    ],
  } as unknown as QraByTeacherPayload;

  it('emits a labeled teacher header row then question member rows', () => {
    const rows = parse(reportToCsv('qra-by-teacher', payload));
    expect(rows[0][0]).toBe('Group');
    expect(rows[1][0]).toBe('Teacher: Ms. Lee');
    expect(rows[1][5]).toBe('80.0%');
    expect(rows[2][0]).toBe('');
    expect(rows[2][1]).toBe('1');
    expect(rows[2][5]).toBe('90.0%');
  });
});

describe('QRA-by-standard-teacher flattener (nested groups)', () => {
  const payload = {
    standard_groups: [
      {
        cpalms_standard: 'MA.912.AR.3.1',
        standard_description: 'Solve linear equations',
        standard_average: 0.7,
        standard_average_pct: '70.0%',
        teacher_groups: [
          {
            section_instructor: 'Mr. Park',
            teacher_standard_average: 0.65,
            teacher_standard_average_pct: '65.0%',
            questions: [
              {
                question_id: 'q1',
                question_no: '1',
                sorting_question_no: 1,
                position_number: '1',
                question: 'Q1',
                correct_answer: 'a',
                grade_average: 0.6,
                grade_average_pct: '60.0%',
                incorrect_choice_details: '',
                incorrect_details_name: '',
                standards: 'MA.912.AR.3.1',
                cpalms_standard: 'MA.912.AR.3.1',
              },
            ],
          },
        ],
      },
    ],
  } as unknown as QraByStandardTeacherPayload;

  it('emits standard header, teacher header, then member rows', () => {
    const rows = parse(reportToCsv('qra-by-standard-teacher', payload));
    expect(rows[1][0]).toBe('Standard: MA.912.AR.3.1');
    expect(rows[1][2]).toBe('Solve linear equations');
    expect(rows[2][0]).toBe('Teacher: Mr. Park');
    expect(rows[2][5]).toBe('65.0%');
    expect(rows[3][1]).toBe('1');
    expect(rows[3][5]).toBe('60.0%');
  });
});

describe('QSR matrix flattener (partial-credit points + subtotal + grand total)', () => {
  // Partial credit: cells carry points_received (may be fractional). Alice has
  // q1=1, q2=0.5 (half credit) → 1.5/2 = 75%; Bob has q1=1, q2 not attempted
  // → 1/1 = 100%. Per-question Score% = SUM(received)/SUM(possible): q1 = 2/2 =
  // 100%, q2 = 0.5/1 = 50%.
  const payload = {
    questions: [
      { question_id: 'q1', question_no: '1' },
      { question_id: 'q2', question_no: '2' },
    ],
    teacher_groups: [
      {
        section_instructor: 'Ms. Lee',
        teacher_score_pct: 0.833333,
        students: [
          {
            user_uid: 'u1',
            user_name: 'Alice',
            score_pct: 0.75,
            cells: { q1: 1, q2: 0.5 },
            band_pct: {},
          },
          {
            user_uid: 'u2',
            user_name: 'Bob',
            score_pct: 1,
            cells: { q1: 1, q2: null },
            band_pct: {},
          },
        ],
        per_question_correct: { q1: 2, q2: 0.5 },
        per_question_possible: { q1: 2, q2: 1 },
        per_question_pct: { q1: 1, q2: 0.5 },
      },
    ],
    grand_total: {
      score_pct: 0.833333,
      per_question_pct: { q1: 1, q2: 0.5 },
    },
  } as unknown as QuestionSummaryMatrixPayload;

  it('renders student rows with partial-credit point cells and labeled subtotal/grand rows', () => {
    const rows = parse(reportToCsv('qsr', payload));
    expect(rows[0]).toEqual(['Student', '1', '2', 'Total %']);
    expect(rows[1][0]).toBe('Teacher: Ms. Lee');
    // Fractional credit renders as the points value (0.5), not a binary 0/1.
    expect(rows[2]).toEqual(['Alice', '1', '0.5', '75.0%']);
    // null cell renders blank, not 0.
    expect(rows[3]).toEqual(['Bob', '1', '', '100.0%']);
    expect(rows[4][0]).toBe('Subtotal: Ms. Lee');
    // Per-question Score% in the subtotal: q1 100%, q2 50%.
    expect(rows[4][1]).toBe('100.0%');
    expect(rows[4][2]).toBe('50.0%');
    expect(rows[4][3]).toBe('83.3%');
    const last = rows[rows.length - 1];
    expect(last[0]).toBe('Grand Total');
    expect(last[1]).toBe('100.0%');
    expect(last[2]).toBe('50.0%');
    expect(last[3]).toBe('83.3%');
  });
});

describe('YTD flattener (student rows × standard columns)', () => {
  const payload = {
    standards: [
      { standard_label: 'MA.1', schoology_standard: 's1', unit_names: '' },
      { standard_label: 'MA.2', schoology_standard: 's2', unit_names: '' },
    ],
    teacher_groups: [
      {
        section_instructor: 'Ms. Lee',
        teacher_score_pct: 0.8,
        students: [
          {
            user_uid: 'u1',
            user_name: 'Alice',
            score_pct: 0.9,
            tests_taken: 3,
            points_received: 9,
            points_possible: 10,
            cells: {
              s1: { points_received: 4, points_possible: 5, score_pct: 0.8 },
              s2: { points_received: 5, points_possible: 5, score_pct: 1 },
            },
          },
        ],
        standard_subtotals: {
          s1: { points_received: 4, points_possible: 5, score_pct: 0.8 },
          s2: { points_received: 5, points_possible: 5, score_pct: 1 },
        },
      },
    ],
    grand_total: {
      points_received: 9,
      points_possible: 10,
      score_pct: 0.9,
      standard_totals: {
        s1: { points_received: 4, points_possible: 5, score_pct: 0.8 },
        s2: { points_received: 5, points_possible: 5, score_pct: 1 },
      },
    },
  } as unknown as YearToDatePerformancePayload;

  it('uses standard labels as columns and points as cell values', () => {
    const rows = parse(reportToCsv('ytd', payload));
    expect(rows[0]).toEqual(['Student', 'Tests Taken', 'MA.1', 'MA.2', 'Total %']);
    expect(rows[1][0]).toBe('Teacher: Ms. Lee');
    expect(rows[2]).toEqual(['Alice', '3', '4', '5', '90.0%']);
    expect(rows[3][0]).toBe('Subtotal: Ms. Lee');
    const last = rows[rows.length - 1];
    expect(last[0]).toBe('Grand Total');
    expect(last[4]).toBe('90.0%');
  });
});

describe('Standard Summary flattener (one row per standard)', () => {
  const payload = {
    standards: [
      {
        schoology_standard: 'MA.912.AR.3.1',
        cpalms_standard: 'MA.912.AR.3.1',
        strand: 'Algebraic Reasoning',
        description: 'Solve <b>linear</b> equations',
        num_questions: 4,
        num_assessments: 2,
        grade_average: 0.82,
      },
    ],
  } as unknown as StandardSummaryPayload;

  it('emits standard, strand, stripped description, totals and percentages', () => {
    const rows = parse(reportToCsv('standard-summary', payload));
    expect(rows[0][0]).toBe('Standard');
    expect(rows[1][0]).toBe('MA.912.AR.3.1');
    expect(rows[1][3]).toBe('Solve linear equations');
    expect(rows[1][4]).toBe('4');
    expect(rows[1][6]).toBe('82.0%');
    expect(rows[1][7]).toBe('18.0%');
  });
});

describe('Strand Summary flattener (one row per strand)', () => {
  const payload = {
    strands_rollup: [
      {
        strand: 'Algebraic Reasoning',
        num_standards: 3,
        num_questions: 12,
        num_assessments: 4,
        grade_average: 0.7,
        incorrect_pct: 0.3,
      },
    ],
  } as unknown as StrandSummaryPayload;

  it('emits strand grain with grade-average and incorrect percentages', () => {
    const rows = parse(reportToCsv('strand-summary', payload));
    expect(rows[1]).toEqual([
      'Algebraic Reasoning',
      '3',
      '12',
      '4',
      '70.0%',
      '30.0%',
    ]);
  });
});

describe('SDD flattener (standards_rollup grain)', () => {
  const payload = {
    standards_rollup: [
      {
        schoology_standard: 'MA.1',
        strand: 'Number',
        num_questions: 5,
        grade_average: 0.6,
      },
      {
        schoology_standard: 'MA.2',
        strand: 'Number',
        num_questions: 0,
        grade_average: null,
      },
    ],
  } as unknown as StandardsDeepDivePayload;

  it('renders one row per standard and blanks unassessed grade averages', () => {
    const rows = parse(reportToCsv('sdd', payload));
    expect(rows[1]).toEqual(['MA.1', 'Number', '5', '60.0%']);
    expect(rows[2]).toEqual(['MA.2', 'Number', '0', '']);
  });
});

describe('IAD flattener (two labeled blocks)', () => {
  const payload = {
    distractors: [
      {
        answer_submission: 'a. <https://img/a.png>',
        students_count: 3,
        share_of_attempts: 0.3,
        share_pct: '30.0%',
        is_correct: false,
      },
      {
        answer_submission: 'b',
        students_count: 7,
        share_of_attempts: 0.7,
        share_pct: '70.0%',
        is_correct: true,
      },
    ],
    student_attempts: [
      {
        user_uid: 'u1',
        user_name: 'Alice',
        answer_submission: 'a',
        correct_answer: 'b',
        is_correct: false,
        points_received: 0,
        points_possible: 1,
        score_pct: 0,
        latest_attempt: '',
      },
    ],
  } as unknown as IncorrectAnswerDetailsPayload;

  it('labels the distractor block then the student-attempt block', () => {
    const rows = parse(reportToCsv('iad', payload));
    expect(rows[0]).toEqual(['Distractors']);
    expect(rows[1]).toEqual(['Answer', '# Students', '% of Attempts', 'Correct?']);
    // Image answer collapses to [image].
    expect(rows[2][0]).toBe('a. [image]');
    expect(rows[2][3]).toBe('No');
    expect(rows[3][3]).toBe('Yes');
    // Blank separator row, then the student-attempt block header.
    const studentHeaderIdx = rows.findIndex((r) => r[0] === 'Student Attempts');
    expect(studentHeaderIdx).toBeGreaterThan(0);
    expect(rows[studentHeaderIdx + 1]).toEqual([
      'Student',
      'Answer',
      'Correct Answer',
      'Correct?',
      'Score %',
    ]);
    expect(rows[studentHeaderIdx + 2]).toEqual(['Alice', 'a', 'b', 'No', '0.0%']);
  });
});
