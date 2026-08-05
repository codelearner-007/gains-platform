import { makeReportMetadata } from '@/lib/reports/report-types';

export const metadata = makeReportMetadata('forward-view');

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
