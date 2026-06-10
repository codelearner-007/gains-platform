import type { Metadata } from 'next';
import { AcceptInvitePage } from '@/components/auth/accept-invite/AcceptInvitePage';

export const metadata: Metadata = {
  title: 'Accept Invitation',
};

export default function Page() {
  return <AcceptInvitePage />;
}
