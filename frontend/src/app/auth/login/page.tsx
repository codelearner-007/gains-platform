import type { Metadata } from 'next';
import { LoginPage } from '@/components/auth/login/LoginPage';
import { serverSettings } from '@/lib/core/server-settings';

export const metadata: Metadata = {
  title: 'Login',
};

export default function Page() {
  // Google sign-in is shown only when the credential is actually configured.
  const googleEnabled = Boolean(serverSettings.SUPABASE_AUTH_EXTERNAL_GOOGLE_CLIENT_ID);
  return <LoginPage googleEnabled={googleEnabled} />;
}
