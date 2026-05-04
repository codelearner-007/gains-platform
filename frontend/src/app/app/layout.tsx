import ProtectedShellLayout from '@/components/common/ProtectedShellLayout';

export default function Layout({ children }: { children: React.ReactNode }) {
  return <ProtectedShellLayout>{children}</ProtectedShellLayout>;
}