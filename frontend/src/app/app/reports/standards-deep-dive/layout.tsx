import { makeReportMetadata } from '@/lib/reports/report-types';

export const metadata = makeReportMetadata('standards-deep-dive');

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
