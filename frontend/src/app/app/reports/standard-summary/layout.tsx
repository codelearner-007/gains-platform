import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Standard Summary | Reports',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
