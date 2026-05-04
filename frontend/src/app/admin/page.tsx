import type { Metadata } from 'next';
import AdminHomePage from '@/components/admin/AdminHomePage';

export const metadata: Metadata = {
  title: 'Dashboard | Admin',
};

export const dynamic = 'force-dynamic';

export default async function AdminPage() {
  return <AdminHomePage />;
}
