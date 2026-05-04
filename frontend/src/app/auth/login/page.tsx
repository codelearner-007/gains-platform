import type { Metadata } from 'next';
import { LoginPage } from '@/components/auth/login/LoginPage';

export const metadata: Metadata = {
  title: 'Login',
};

export default function Page() {
  return <LoginPage />;
}
