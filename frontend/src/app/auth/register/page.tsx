import { redirect } from 'next/navigation';

// Public self-signup is disabled — GAINS is invite-only.
// Any attempt to reach the registration page is redirected to login.
export default function Page() {
  redirect('/auth/login');
}
