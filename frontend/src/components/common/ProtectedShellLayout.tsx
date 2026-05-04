import AppLayout from '@/components/common/AppLayout';
import { Providers } from '@/components/common/Providers';

export default function ProtectedShellLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  return (
    <Providers>
      <AppLayout>{children}</AppLayout>
    </Providers>
  );
}

