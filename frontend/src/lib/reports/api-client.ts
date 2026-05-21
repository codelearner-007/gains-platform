import type {
  AlignmentDataQualityReport,
  AssessmentFilters,
  AssessmentListRow,
  GradeRow,
  IncorrectAnswerDetailsPayload,
  QuestionResponseAnalysisPayload,
  SectionRow,
  SessionRow,
  StandardSummaryFilters,
  StandardSummaryPayload,
  StandardsDeepDivePayload,
  StrandSummaryFilters,
  StrandSummaryPayload,
  SubjectRow,
  YearToDatePerformancePayload,
} from './types';

async function handleResponse<T>(r: Response): Promise<T> {
  if (!r.ok) {
    const body = await r.text().catch(() => '');
    console.error('[reports api]', r.status, body);
    const userMessage =
      r.status === 401
        ? 'You need to sign in.'
        : r.status === 403
          ? 'You do not have access to this report.'
          : r.status === 404
            ? 'Report not found.'
            : r.status >= 500
              ? 'The server is having trouble loading this report. Please try again.'
              : 'Could not load the report.';
    throw new Error(userMessage);
  }
  return r.json() as Promise<T>;
}

function buildQuery(params?: Record<string, string | undefined> | object): string {
  if (!params) return '';
  const entries = Object.entries(params).filter(
    ([, v]) => v !== undefined && v !== null && v !== '',
  ) as [string, string][];
  if (entries.length === 0) return '';
  return `?${new URLSearchParams(entries).toString()}`;
}

export const reportsApi = {
  qra: (itemId: string) =>
    fetch(
      `/api/v1/reports/question-response-analysis/${encodeURIComponent(itemId)}`,
      { credentials: 'include' },
    ).then(handleResponse<QuestionResponseAnalysisPayload>),

  sdd: (itemId: string) =>
    fetch(
      `/api/v1/reports/standards-deep-dive/${encodeURIComponent(itemId)}`,
      { credentials: 'include' },
    ).then(handleResponse<StandardsDeepDivePayload>),

  ytd: () =>
    fetch('/api/v1/reports/year-to-date-performance', {
      credentials: 'include',
    }).then(handleResponse<YearToDatePerformancePayload>),

  standardSummary: (filters?: StandardSummaryFilters) =>
    fetch(`/api/v1/reports/standard-summary${buildQuery(filters)}`, {
      credentials: 'include',
    }).then(handleResponse<StandardSummaryPayload>),

  strandSummary: (filters?: StrandSummaryFilters) =>
    fetch(`/api/v1/reports/strand-summary${buildQuery(filters)}`, {
      credentials: 'include',
    }).then(handleResponse<StrandSummaryPayload>),

  alignmentDataQuality: () =>
    fetch('/api/v1/reports/data-quality/standards-alignment', {
      credentials: 'include',
    }).then(handleResponse<AlignmentDataQualityReport>),

  iad: (itemId: string, questionId: string) =>
    fetch(
      `/api/v1/reports/incorrect-answer-details/${encodeURIComponent(itemId)}/${encodeURIComponent(questionId)}`,
      { credentials: 'include' },
    ).then(handleResponse<IncorrectAnswerDetailsPayload>),

  assessments: (filters?: AssessmentFilters) =>
    fetch(`/api/v1/assessments${buildQuery(filters)}`, {
      credentials: 'include',
    }).then(handleResponse<AssessmentListRow[]>),

  sessions: () =>
    fetch('/api/v1/dim/sessions', { credentials: 'include' }).then(
      handleResponse<SessionRow[]>,
    ),

  subjects: () =>
    fetch('/api/v1/dim/subjects', { credentials: 'include' }).then(
      handleResponse<SubjectRow[]>,
    ),

  grades: () =>
    fetch('/api/v1/dim/grades', { credentials: 'include' }).then(
      handleResponse<GradeRow[]>,
    ),

  sections: () =>
    fetch('/api/v1/dim/sections', { credentials: 'include' }).then(
      handleResponse<SectionRow[]>,
    ),
};

export const reportsKeys = {
  all: ['reports'] as const,
  qra: (itemId: string) => [...reportsKeys.all, 'qra', itemId] as const,
  sdd: (itemId: string) => [...reportsKeys.all, 'sdd', itemId] as const,
  ytd: () => [...reportsKeys.all, 'ytd'] as const,
  iad: (itemId: string, questionId: string) =>
    [...reportsKeys.all, 'iad', itemId, questionId] as const,
  standardSummary: (filters?: StandardSummaryFilters) =>
    [...reportsKeys.all, 'standardSummary', filters ?? {}] as const,
  strandSummary: (filters?: StrandSummaryFilters) =>
    [...reportsKeys.all, 'strandSummary', filters ?? {}] as const,
  alignmentDataQuality: () =>
    [...reportsKeys.all, 'dq', 'standards-alignment'] as const,
  assessments: (filters?: AssessmentFilters) =>
    [...reportsKeys.all, 'assessments', filters ?? {}] as const,
  sessions: () => [...reportsKeys.all, 'dim', 'sessions'] as const,
  subjects: () => [...reportsKeys.all, 'dim', 'subjects'] as const,
  grades: () => [...reportsKeys.all, 'dim', 'grades'] as const,
  sections: () => [...reportsKeys.all, 'dim', 'sections'] as const,
};
