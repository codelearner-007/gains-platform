import { ReportsQueryClientProvider } from '@/lib/reports/query-client';

export default function ReportsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ReportsQueryClientProvider>
      {children}
    </ReportsQueryClientProvider>
  );
}
