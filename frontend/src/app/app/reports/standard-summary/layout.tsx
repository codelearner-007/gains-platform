import { makeReportMetadata } from '@/lib/reports/report-types';

export const metadata = makeReportMetadata('standard-summary');

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
