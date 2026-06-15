import { makeReportMetadata } from '@/lib/reports/report-types';

export const metadata = makeReportMetadata('year-to-date-performance');

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
