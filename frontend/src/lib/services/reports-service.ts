import type {
  AssessmentFilters,
  StandardSummaryFilters,
  StrandSummaryFilters,
} from '@/lib/reports/types';

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

export { reportsApi } from '@/lib/reports/api-client';
