import type { Metadata } from 'next';

export const metadata: Metadata = {
  title: 'Year-To-Date Performance | Reports',
};

export default function Layout({ children }: { children: React.ReactNode }) {
  return children;
}
