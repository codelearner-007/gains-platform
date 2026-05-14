import type { AssessmentFilters } from '@/lib/reports/types';

export const reportsKeys = {
  all: ['reports'] as const,
  qra: (itemId: string) => [...reportsKeys.all, 'qra', itemId] as const,
  sdd: (itemId: string) => [...reportsKeys.all, 'sdd', itemId] as const,
  ytd: () => [...reportsKeys.all, 'ytd'] as const,
  assessments: (filters?: AssessmentFilters) =>
    [...reportsKeys.all, 'assessments', filters ?? {}] as const,
  sessions: () => [...reportsKeys.all, 'dim', 'sessions'] as const,
  subjects: () => [...reportsKeys.all, 'dim', 'subjects'] as const,
  grades: () => [...reportsKeys.all, 'dim', 'grades'] as const,
  sections: () => [...reportsKeys.all, 'dim', 'sections'] as const,
};

export { reportsApi } from '@/lib/reports/api-client';
