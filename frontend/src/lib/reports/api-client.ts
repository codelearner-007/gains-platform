import type {
  AccessibleSchool,
  AlignmentDataQualityReport,
  AssessmentFilters,
  AssessmentSummaryPage,
  AssessmentTypeRow,
  DashboardOverviewPayload,
  DashboardStrandRowsPage,
  ForwardViewFilters,
  ForwardViewPayload,
  GradeRow,
  IncorrectAnswerDetailsPayload,
  InstructorRow,
  QraByStandardTeacherPayload,
  QraByTeacherPayload,
  QraPaginatedPayload,
  QuestionResponseAnalysisPayload,
  QuestionSummaryMatrixPayload,
  SectionRow,
  SessionRow,
  StandardSummaryFilters,
  PerStudentReportPayload,
  StandardSummaryPayload,
  StandardsDeepDivePayload,
  StrandSummaryFilters,
  StrandSummaryPayload,
  StudentBrowsePage,
  SubjectRow,
  YearToDatePerformancePayload,
} from './types';

/** Active filter scope that narrows the Section list to the sections that
 *  actually taught this session/subject/grade/category. All parts optional. */
export interface SectionScope {
  session?: string;
  subject?: string;
  grade?: string;
  category?: string;
}

/** Server-side paging/sort/search options for the assessment summary grid. */
export interface AssessmentSummaryQuery {
  q?: string;
  sort?: string; // 'date' | 'item' | 'grade' | 'students' | 'average'
  dir?: 'asc' | 'desc';
  /** Splits the By-Assessment grid: 'assessment' (non-quiz), 'quiz', or 'all'. */
  kind?: 'assessment' | 'quiz' | 'all';
  limit?: number;
  offset?: number;
}

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
  accessibleSchools: () =>
    fetch('/api/v1/schools/accessible', { credentials: 'include' }).then(
      handleResponse<AccessibleSchool[]>,
    ),

  qra: (itemId: string, schoolId?: string, instructor?: string) =>
    fetch(
      `/api/v1/reports/question-response-analysis/${encodeURIComponent(itemId)}${buildQuery({ school_id: schoolId, instructor })}`,
      { credentials: 'include' },
    ).then(handleResponse<QuestionResponseAnalysisPayload>),

  sdd: (itemId: string, schoolId?: string, instructor?: string) =>
    fetch(
      `/api/v1/reports/standards-deep-dive/${encodeURIComponent(itemId)}${buildQuery({ school_id: schoolId, instructor })}`,
      { credentials: 'include' },
    ).then(handleResponse<StandardsDeepDivePayload>),

  ytd: (filters?: AssessmentFilters) =>
    fetch(
      `/api/v1/reports/year-to-date-performance${buildQuery(filters)}`,
      { credentials: 'include' },
    ).then(handleResponse<YearToDatePerformancePayload>),

  // ``cardsOnly`` skips the KPI cube reads (incl. the total_students fact
  // scan) — the report page renders only the card grid, so it passes true;
  // the dashboard omits it to get the full KPI block for its stat cards.
  standardSummary: (filters?: StandardSummaryFilters, cardsOnly?: boolean) =>
    fetch(
      `/api/v1/reports/standard-summary${buildQuery({
        ...filters,
        cards_only: cardsOnly ? 'true' : undefined,
      })}`,
      { credentials: 'include' },
    ).then(handleResponse<StandardSummaryPayload>),

  strandSummary: (filters?: StrandSummaryFilters) =>
    fetch(`/api/v1/reports/strand-summary${buildQuery(filters)}`, {
      credentials: 'include',
    }).then(handleResponse<StrandSummaryPayload>),

  // ``threshold`` arrives as a fraction string (e.g. "0.7"); ``session`` may be
  // absent (the backend defaults to the current/latest session and echoes it).
  // All scoping (school, filters, threshold) rides the query string via ``buildQuery``.
  forwardView: (filters?: ForwardViewFilters) =>
    fetch(`/api/v1/reports/forward-view${buildQuery(filters)}`, {
      credentials: 'include',
    }).then(handleResponse<ForwardViewPayload>),

  alignmentDataQuality: () =>
    fetch('/api/v1/reports/data-quality/standards-alignment', {
      credentials: 'include',
    }).then(handleResponse<AlignmentDataQualityReport>),

  iad: (itemId: string, questionId: string, schoolId?: string) =>
    fetch(
      `/api/v1/reports/incorrect-answer-details/${encodeURIComponent(itemId)}/${encodeURIComponent(questionId)}${buildQuery({ school_id: schoolId })}`,
      { credentials: 'include' },
    ).then(handleResponse<IncorrectAnswerDetailsPayload>),

  questionSummaryPaginated: (itemId: string, schoolId?: string) =>
    fetch(
      `/api/v1/reports/question-summary-paginated/${encodeURIComponent(itemId)}${buildQuery({ school_id: schoolId })}`,
      { credentials: 'include' },
    ).then(handleResponse<QuestionSummaryMatrixPayload>),

  qraPaginated: (itemId: string, schoolId?: string) =>
    fetch(
      `/api/v1/reports/question-response-analysis-paginated/${encodeURIComponent(itemId)}${buildQuery({ school_id: schoolId })}`,
      { credentials: 'include' },
    ).then(handleResponse<QraPaginatedPayload>),

  qraByTeacher: (itemId: string, schoolId?: string) =>
    fetch(
      `/api/v1/reports/question-response-analysis-by-teacher/${encodeURIComponent(itemId)}${buildQuery({ school_id: schoolId })}`,
      { credentials: 'include' },
    ).then(handleResponse<QraByTeacherPayload>),

  qraByStandardTeacher: (itemId: string, schoolId?: string) =>
    fetch(
      `/api/v1/reports/question-response-analysis-by-standard-and-teacher/${encodeURIComponent(itemId)}${buildQuery({ school_id: schoolId })}`,
      { credentials: 'include' },
    ).then(handleResponse<QraByStandardTeacherPayload>),

  assessmentSummaries: (
    filters: AssessmentFilters | undefined,
    schoolId: string | undefined,
    opts: AssessmentSummaryQuery,
  ) =>
    fetch(
      `/api/v1/assessments/summary-list${buildQuery({
        ...filters,
        school_id: schoolId,
        q: opts.q,
        sort: opts.sort,
        dir: opts.dir,
        kind: opts.kind,
        limit: opts.limit != null ? String(opts.limit) : undefined,
        offset: opts.offset != null ? String(opts.offset) : undefined,
      })}`,
      { credentials: 'include' },
    ).then(handleResponse<AssessmentSummaryPage>),

  /** Subject KPI cards (per-subject grade-average) + dataset-refresh timestamp.
   *  School-wide (no section/instructor grain), scoped by year/type/grade. */
  dashboardOverview: (
    filters: Pick<AssessmentFilters, 'session' | 'category' | 'grade' | 'school_id'> | undefined,
  ) =>
    fetch(`/api/v1/reports/dashboard-overview${buildQuery(filters)}`, {
      credentials: 'include',
    }).then(handleResponse<DashboardOverviewPayload>),

  /** One server-paginated page of the legacy Performance-by-Strand grid. */
  strandRows: (
    filters: AssessmentFilters | undefined,
    schoolId: string | undefined,
    opts: AssessmentSummaryQuery,
  ) =>
    fetch(
      `/api/v1/reports/strand-rows${buildQuery({
        ...filters,
        school_id: schoolId,
        q: opts.q,
        sort: opts.sort,
        dir: opts.dir,
        limit: opts.limit != null ? String(opts.limit) : undefined,
        offset: opts.offset != null ? String(opts.offset) : undefined,
      })}`,
      { credentials: 'include' },
    ).then(handleResponse<DashboardStrandRowsPage>),

  /** One server-paginated page of the dashboard "By Students" roster. Shares
   *  the By-Assessment filter set; pivots to one summary row per student. */
  studentsBrowse: (
    filters: AssessmentFilters | undefined,
    schoolId: string | undefined,
    opts: AssessmentSummaryQuery,
  ) =>
    fetch(
      `/api/v1/students/browse${buildQuery({
        ...filters,
        school_id: schoolId,
        q: opts.q,
        sort: opts.sort,
        dir: opts.dir,
        limit: opts.limit != null ? String(opts.limit) : undefined,
        offset: opts.offset != null ? String(opts.offset) : undefined,
      })}`,
      { credentials: 'include' },
    ).then(handleResponse<StudentBrowsePage>),

  /** Full multi-subject report for one student (canonical latest-attempt grain). */
  studentReport: (
    uid: string,
    session: string | undefined,
    schoolId: string | undefined,
  ) =>
    fetch(
      `/api/v1/students/${encodeURIComponent(uid)}/report${buildQuery({
        session,
        school_id: schoolId,
      })}`,
      { credentials: 'include' },
    ).then(handleResponse<PerStudentReportPayload>),

  sessions: (schoolId?: string) =>
    fetch(`/api/v1/dim/sessions${buildQuery({ school_id: schoolId })}`, {
      credentials: 'include',
    }).then(handleResponse<SessionRow[]>),

  assessmentTypes: (schoolId?: string) =>
    fetch(`/api/v1/dim/assessment-types${buildQuery({ school_id: schoolId })}`, {
      credentials: 'include',
    }).then(handleResponse<AssessmentTypeRow[]>),

  instructors: (schoolId?: string) =>
    fetch(`/api/v1/dim/instructors${buildQuery({ school_id: schoolId })}`, {
      credentials: 'include',
    }).then(handleResponse<InstructorRow[]>),

  subjects: (schoolId?: string) =>
    fetch(`/api/v1/dim/subjects${buildQuery({ school_id: schoolId })}`, {
      credentials: 'include',
    }).then(handleResponse<SubjectRow[]>),

  grades: (schoolId?: string) =>
    fetch(`/api/v1/dim/grades${buildQuery({ school_id: schoolId })}`, {
      credentials: 'include',
    }).then(handleResponse<GradeRow[]>),

  // Scoped section list: the backend narrows `cube_user_summary` to the
  // session/subject/grade/category before grouping, so the caller passes the
  // active filter scope and receives only the sections that actually taught it.
  sections: (schoolId?: string, scope?: SectionScope) =>
    fetch(
      `/api/v1/dim/sections${buildQuery({
        school_id: schoolId,
        session: scope?.session,
        subject: scope?.subject,
        grade: scope?.grade,
        category: scope?.category,
      })}`,
      { credentials: 'include' },
    ).then(handleResponse<SectionRow[]>),
};

export const reportsKeys = {
  all: ['reports'] as const,
  schools: () => [...reportsKeys.all, 'schools', 'accessible'] as const,
  qra: (itemId: string, schoolId?: string, instructor?: string) =>
    [...reportsKeys.all, 'qra', itemId, schoolId ?? null, instructor ?? null] as const,
  sdd: (itemId: string, schoolId?: string, instructor?: string) =>
    [...reportsKeys.all, 'sdd', itemId, schoolId ?? null, instructor ?? null] as const,
  ytd: (filters?: AssessmentFilters) =>
    [...reportsKeys.all, 'ytd', filters ?? {}] as const,
  iad: (itemId: string, questionId: string, schoolId?: string) =>
    [...reportsKeys.all, 'iad', itemId, questionId, schoolId ?? null] as const,
  questionSummaryPaginated: (itemId: string, schoolId?: string) =>
    [...reportsKeys.all, 'qsr-paginated', itemId, schoolId ?? null] as const,
  qraPaginated: (itemId: string, schoolId?: string) =>
    [...reportsKeys.all, 'qra-paginated', itemId, schoolId ?? null] as const,
  qraByTeacher: (itemId: string, schoolId?: string) =>
    [...reportsKeys.all, 'qra-by-teacher', itemId, schoolId ?? null] as const,
  qraByStandardTeacher: (itemId: string, schoolId?: string) =>
    [...reportsKeys.all, 'qra-by-std-teacher', itemId, schoolId ?? null] as const,
  standardSummary: (filters?: StandardSummaryFilters, cardsOnly?: boolean) =>
    [...reportsKeys.all, 'standardSummary', filters ?? {}, cardsOnly ?? false] as const,
  strandSummary: (filters?: StrandSummaryFilters) =>
    [...reportsKeys.all, 'strandSummary', filters ?? {}] as const,
  // The full filter object (incl. school_id + threshold fraction) is embedded
  // so any threshold/filter change is a distinct cache entry.
  forwardView: (filters?: ForwardViewFilters) =>
    [...reportsKeys.all, 'forwardView', filters ?? {}] as const,
  dashboardOverview: (
    filters?: Pick<AssessmentFilters, 'session' | 'category' | 'grade' | 'school_id'>,
  ) => [...reportsKeys.all, 'dashboard-overview', filters ?? {}] as const,
  strandRows: (
    filters?: AssessmentFilters,
    schoolId?: string,
    opts?: { q?: string; sort?: string; dir?: string },
  ) =>
    [
      ...reportsKeys.all,
      'strand-rows',
      filters ?? {},
      schoolId ?? null,
      { q: opts?.q ?? '', sort: opts?.sort ?? 'date', dir: opts?.dir ?? 'desc' },
    ] as const,
  alignmentDataQuality: () =>
    [...reportsKeys.all, 'dq', 'standards-alignment'] as const,
  assessmentSummaries: (
    filters?: AssessmentFilters,
    schoolId?: string,
    opts?: { q?: string; sort?: string; dir?: string; kind?: string },
  ) =>
    [
      ...reportsKeys.all,
      'assessment-summaries',
      filters ?? {},
      schoolId ?? null,
      {
        q: opts?.q ?? '',
        sort: opts?.sort ?? 'date',
        dir: opts?.dir ?? 'desc',
        kind: opts?.kind ?? 'all',
      },
    ] as const,
  studentsBrowse: (
    filters?: AssessmentFilters,
    schoolId?: string,
    opts?: { q?: string; sort?: string; dir?: string },
  ) =>
    [
      ...reportsKeys.all,
      'students-browse',
      filters ?? {},
      schoolId ?? null,
      { q: opts?.q ?? '', sort: opts?.sort ?? 'name', dir: opts?.dir ?? 'asc' },
    ] as const,
  studentReport: (uid: string, session?: string, schoolId?: string) =>
    [...reportsKeys.all, 'student-report', uid, session ?? null, schoolId ?? null] as const,
  sessions: (schoolId?: string) =>
    [...reportsKeys.all, 'dim', 'sessions', schoolId ?? null] as const,
  assessmentTypes: (schoolId?: string) =>
    [...reportsKeys.all, 'dim', 'assessment-types', schoolId ?? null] as const,
  instructors: (schoolId?: string) =>
    [...reportsKeys.all, 'dim', 'instructors', schoolId ?? null] as const,
  subjects: (schoolId?: string) =>
    [...reportsKeys.all, 'dim', 'subjects', schoolId ?? null] as const,
  grades: (schoolId?: string) =>
    [...reportsKeys.all, 'dim', 'grades', schoolId ?? null] as const,
  // The scope object is embedded so each session/subject/grade/category is a
  // distinct cache entry (the section list changes as the scope narrows).
  sections: (schoolId?: string, scope?: SectionScope) =>
    [...reportsKeys.all, 'dim', 'sections', schoolId ?? null, scope ?? {}] as const,
};
