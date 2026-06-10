import { redirect } from 'next/navigation';

// The verify-email page was only reachable from the (now removed) public signup flow.
// Invite-only provisioning handles confirmation links directly via /api/auth/callback.
export default function Page() {
  redirect('/auth/login');
}
