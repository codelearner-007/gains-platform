import type { Metadata } from 'next';
import { ForgotPasswordPage } from '@/components/auth/forgot-password/ForgotPasswordPage';

export const metadata: Metadata = {
  title: 'Forgot Password',
};

export default function Page() {
  return <ForgotPasswordPage />;
}
