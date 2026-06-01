export default function ReportsLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  // The TanStack QueryClient is provided higher up in `ProtectedShellLayout`
  // so the school switcher and report pages share one cache (school changes
  // invalidate report queries via the `schoolId` query-key segment).
  return <>{children}</>;
}
