import { describe, expect, it } from 'vitest';
import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import QuestionDetailTable from '@/components/app/modules/reports/qra/QuestionDetailTable';
import DistractorTable from '@/components/app/modules/reports/iad/DistractorTable';
import StudentAttemptTable from '@/components/app/modules/reports/iad/StudentAttemptTable';
import type {
  IadDistractorRow,
  IadStudentAttempt,
  QuestionOverall,
} from '@/lib/reports/types';

// These tests pin the legacy-correct DEFAULT sort order of the report tables
// (Wave A2). `renderToStaticMarkup` captures the first render, which is the
// default-sorted state produced by `useTableSort`. We assert on the order in
// which identifying values appear in the markup.

function orderOf(html: string, pattern: RegExp): string[] {
  return [...html.matchAll(pattern)].map((m) => m[1]);
}

function makeQuestion(
  question_no: string,
  grade_average: number,
): QuestionOverall {
  return {
    question_id: `q-${question_no}`,
    question_no,
    position_number: '1',
    question: `Stem ${question_no}`,
    question_type: 'mcq',
    correct_answer: 'A',
    total_possible_point: 1,
    total_score: 1,
    grade_average,
    percentage_incorrect: 1 - grade_average,
    incorrect_choice_details: '',
    incorrect_details_name: '',
    standards: 'MA.912.AR.3.1',
    standard_raw: 'MA.912.AR.3.1',
    description: '',
  };
}

describe('QRA QuestionDetailTable default sort', () => {
  it('defaults to question-number ascending (Q1 → Q18), not % Correct', () => {
    // Deliberately shuffled, with the lowest % first to prove we are NOT
    // sorting by grade_average ascending (the old default).
    const questions = [
      makeQuestion('12', 0.278),
      makeQuestion('3', 0.9),
      makeQuestion('1', 0.5),
      makeQuestion('18', 1),
      makeQuestion('2', 0.4),
    ];
    // No itemId → the No cell renders a plain <div>{question_no}</div>.
    const html = renderToStaticMarkup(
      createElement(QuestionDetailTable, { questions }),
    );
    const order = orderOf(
      html,
      /<div class="px-2 py-2">(\d+)<\/div>/g,
    );
    expect(order).toEqual(['1', '2', '3', '12', '18']);
  });
});

describe('IAD DistractorTable default sort', () => {
  it('defaults to # Students descending (legacy hardcoded DESC)', () => {
    const rows: IadDistractorRow[] = [
      { answer_submission: 'a', students_count: 3, share_of_attempts: 0.3, share_pct: '30%', is_correct: false },
      { answer_submission: 'b', students_count: 9, share_of_attempts: 0.6, share_pct: '60%', is_correct: true },
      { answer_submission: 'c', students_count: 1, share_of_attempts: 0.1, share_pct: '10%', is_correct: false },
    ];
    const html = renderToStaticMarkup(createElement(DistractorTable, { rows }));
    // # Students cell: a right-aligned, bold td containing the bare count.
    const counts = orderOf(
      html,
      /font-weight:600">(\d+)<\/td>/g,
    ).map(Number);
    expect(counts).toEqual([9, 3, 1]);
  });
});

function makeAttempt(
  user_name: string,
  is_correct: boolean,
): IadStudentAttempt {
  return {
    user_uid: `u-${user_name}`,
    user_name,
    answer_submission: is_correct ? 'A' : 'B',
    correct_answer: 'A',
    is_correct,
    points_received: is_correct ? 1 : 0,
    points_possible: 1,
    score_pct: is_correct ? 1 : 0,
    latest_attempt: '2025-09-01T10:00:00Z',
  };
}

describe('IAD StudentAttemptTable default view + sort', () => {
  const attempts: IadStudentAttempt[] = [
    makeAttempt('Charlie', false),
    makeAttempt('Alice', false),
    makeAttempt('Bob', true), // correct → excluded from default "Wrong only"
    makeAttempt('Dana', false),
  ];

  it('defaults to "Wrong only" view (excludes correct attempts)', () => {
    const html = renderToStaticMarkup(
      createElement(StudentAttemptTable, { attempts }),
    );
    // Active tab carries bg-black text-white; "Wrong only" must be active.
    expect(html).toMatch(
      /Wrong only \(3\)<\/button>/,
    );
    // The active "Wrong only" button is styled active (black bg).
    const wrongActive = /bg-black text-white"[^>]*>\s*Wrong only/;
    expect(html).toMatch(wrongActive);
    // Bob is correct, so he must NOT appear in the default (wrong-only) view.
    expect(html).not.toContain('>Bob<');
  });

  it('defaults to Student name ascending', () => {
    const html = renderToStaticMarkup(
      createElement(StudentAttemptTable, { attempts }),
    );
    // Student name cell: bold td.
    const names = orderOf(html, /font-weight:600">([A-Za-z]+)<\/td>/g);
    expect(names).toEqual(['Alice', 'Charlie', 'Dana']);
  });
});
