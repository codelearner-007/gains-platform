import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Standards Deep Dive | Reports',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
