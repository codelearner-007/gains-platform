import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Year To Date - Longitudinal Report',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
