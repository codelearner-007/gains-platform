import { makeReportMetadata } from '@/lib/reports/report-types';

export const metadata = makeReportMetadata('question-response-analysis-by-teacher');

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
