import { ReportsQueryClientProvider } from '@/lib/reports/query-client';
import ReportsNav from '@/components/app/modules/reports/reports-nav';

export default function ReportsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <ReportsQueryClientProvider>
      <div className="space-y-2">
        <ReportsNav />
        {children}
      </div>
    </ReportsQueryClientProvider>
  );
}
