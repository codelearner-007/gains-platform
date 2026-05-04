import type { Metadata } from 'next';
import { SignupPage } from '@/components/auth/signup/SignupPage';

export const metadata: Metadata = {
  title: 'Register',
};

export default function Page() {
  return <SignupPage />;
}
