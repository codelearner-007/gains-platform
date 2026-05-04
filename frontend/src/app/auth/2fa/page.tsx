import type { Metadata } from 'next';
import { MFAVerificationPage } from '@/components/auth/mfa/MFAVerificationPage';
import { Suspense } from 'react';

export const metadata: Metadata = {
  title: 'Two-Factor Authentication',
};

export default function Page() {
  return (
    <Suspense
      fallback={
        <div className="w-full max-w-md flex justify-center items-center p-8">
          <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-primary"></div>
        </div>
      }
    >
      <MFAVerificationPage />
    </Suspense>
  );
}
