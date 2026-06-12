import type { Metadata } from 'next';
import { getReportBySlug } from '@/lib/reports/report-types';

export const metadata: Metadata = {
  title: getReportBySlug('standard-summary').canonicalName,
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
