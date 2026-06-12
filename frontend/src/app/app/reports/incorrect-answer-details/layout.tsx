import { makeReportMetadata } from '@/lib/reports/report-types';

export const metadata = makeReportMetadata('incorrect-answer-details');

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
