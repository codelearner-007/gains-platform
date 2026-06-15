import type { Metadata } from 'next';

export const metadata: Metadata = {
  // Override the root "Starter Template" branding for the whole report family.
  // Child report layouts set string titles (e.g. "Standard Summary"), which
  // this template wraps as "Standard Summary | GAINS Reports".
  title: {
    default: 'GAINS Reports',
    template: '%s | GAINS Reports',
  },
};

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
