import type { Metadata } from 'next';
import { VerifyEmailPage } from '@/components/auth/verify-email/VerifyEmailPage';

export const metadata: Metadata = {
  title: 'Verify Email',
};

export default function Page() {
  return <VerifyEmailPage />;
}
