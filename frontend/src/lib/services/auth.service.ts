import { apiClient, ApiError } from './api-client';
import { trackEvent } from '@/lib/analytics/ga';
import { AnalyticsEvent } from '@/lib/analytics/events';
import type {
  LoginCredentials,
  RegisterData,
  AuthResponse,
  ForgotPasswordData,
  ResetPasswordData,
  CurrentUserResponse,
  MFAStatusResponse,
  MFAFactorsResponse,
} from '@/lib/types/auth.types';

export const authService = {
  async getCurrentUser(): Promise<CurrentUserResponse> {
    return apiClient.get<CurrentUserResponse>('/auth/me');
  },

  async login(credentials: LoginCredentials): Promise<AuthResponse> {
    try {
      const result = await apiClient.post<AuthResponse>('/auth/login', credentials);
      trackEvent(AnalyticsEvent.login_success, {
        user_id: result.user?.id,
        source: 'auth_login',
      });
      return result;
    } catch (err) {
      const status_code = err instanceof ApiError ? err.status : undefined;
      const error_kind =
        err instanceof ApiError ? 'api_error' : err instanceof TypeError ? 'network_error' : 'unknown_error';
      trackEvent(AnalyticsEvent.login_failed, {
        source: 'auth_login',
        status_code,
        error_kind,
      });
      throw err;
    }
  },

  async register(data: RegisterData): Promise<AuthResponse & { message?: string }> {
    try {
      const result = await apiClient.post<AuthResponse & { message?: string }>('/auth/register', data);
      trackEvent(AnalyticsEvent.signup_success, {
        user_id: result.user?.id,
        source: 'auth_register',
      });
      return result;
    } catch (err) {
      const status_code = err instanceof ApiError ? err.status : undefined;
      const error_kind =
        err instanceof ApiError ? 'api_error' : err instanceof TypeError ? 'network_error' : 'unknown_error';
      trackEvent(AnalyticsEvent.signup_failed, {
        source: 'auth_register',
        status_code,
        error_kind,
      });
      throw err;
    }
  },

  async resendVerificationEmail(email: string): Promise<{ message: string }> {
    return apiClient.post('/auth/resend-verification', { email });
  },

  async logout(): Promise<{ message: string }> {
    return apiClient.post<{ message: string }>('/auth/logout');
  },

  async forgotPassword(data: ForgotPasswordData): Promise<{ message: string }> {
    return apiClient.post('/auth/forgot-password', data);
  },

  async resetPassword(data: ResetPasswordData): Promise<{ message: string }> {
    return apiClient.post('/auth/reset-password', data);
  },

  async exchangeCodeForSession(code: string): Promise<void> {
    await apiClient.post('/auth/callback', { code });
  },

  // MFA Management
  async listMFAFactors(): Promise<MFAFactorsResponse> {
    return apiClient.get<MFAFactorsResponse>('/auth/mfa/factors');
  },

  async enrollMFAFactor(friendlyName: string): Promise<{ factorId: string; qrCode: string }> {
    return apiClient.post('/auth/mfa/enroll', { friendlyName });
  },

  async challengeMFAFactor(factorId: string): Promise<{ challengeId: string }> {
    return apiClient.post('/auth/mfa/challenge', { factorId });
  },

  async verifyMFAFactor(factorId: string, challengeId: string, code: string): Promise<{ success: boolean }> {
    return apiClient.post('/auth/mfa/verify', { factorId, challengeId, code });
  },

  async unenrollMFAFactor(factorId: string): Promise<{ success: boolean }> {
    return apiClient.post('/auth/mfa/unenroll', { factorId });
  },

  async getMFAStatus(): Promise<MFAStatusResponse> {
    return apiClient.get<MFAStatusResponse>('/auth/mfa/status');
  },

  /**
   * OAuth / SSO sign-in. Triggers a full-page redirect to the provider; control
   * returns to /api/auth/callback?next=... after the user authorizes.
   *
   * `next` is the in-app destination. The callback route enforces an allowlist
   * before redirecting, so clients cannot use this for an open-redirect.
   */
  async signInWithOAuth(
    provider: 'github' | 'google',
    next: string = '/app',
  ): Promise<void> {
    // Mirror the server-side allowlist (see app/api/auth/callback/route.ts).
    // Anything other than these prefixes is a bug at the call site.
    const ALLOWED_NEXT_PREFIXES = ['/app', '/admin', '/auth/2fa', '/auth/reset-password'];
    const isSafe =
      next.startsWith('/') &&
      !next.startsWith('//') &&
      !next.startsWith('/\\') &&
      ALLOWED_NEXT_PREFIXES.some(
        (p) => next === p || next.startsWith(`${p}/`) || next.startsWith(`${p}?`),
      );
    if (!isSafe) {
      throw new Error(`signInWithOAuth: refused unsafe next path "${next}"`);
    }

    const { createSPAClient } = await import('@/lib/supabase/client');
    const supabase = createSPAClient();

    const callback = `${window.location.origin}/api/auth/callback?next=${encodeURIComponent(next)}`;

    const { error } = await supabase.auth.signInWithOAuth({
      provider,
      options: { redirectTo: callback },
    });

    if (error) throw error;
  },

  /**
   * Send a one-time sign-in link. The server route always returns the same
   * generic message to avoid account enumeration.
   */
  async sendMagicLink(email: string): Promise<{ message: string }> {
    return apiClient.post<{ message: string }>('/auth/magic-link', { email });
  },
};
