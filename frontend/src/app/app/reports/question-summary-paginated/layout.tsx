import { makeReportMetadata } from '@/lib/reports/report-types';

export const metadata = makeReportMetadata('question-summary-paginated');

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
