'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { useGlobal } from '@/lib/context/GlobalContext';
import { authService } from '@/lib/services/auth.service';
import type { LoginCredentials, RegisterData } from '@/lib/types/auth.types';

export function useAuth() {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const router = useRouter();
  const { clearUser, setAuthFromLogin } = useGlobal();

  const login = async (data: LoginCredentials) => {
    setLoading(true);
    setError(null);
    try {
      const response = await authService.login(data);

      // Update global auth state immediately (no extra fetch needed).
      // The response no longer includes session tokens (only safe user metadata).
      setAuthFromLogin({
        user: response.user
          ? {
              id: response.user.id,
              email: (response.user.email as string) ?? null,
              user_metadata: response.user.user_metadata,
              app_metadata: response.user.app_metadata,
            }
          : null,
        mfaRequired: !!response.requiresMFA,
      });

      // Check if MFA verification is required
      if (response.requiresMFA) {
        router.push('/auth/2fa?returnTo=/app');
      } else {
        router.push('/app');
      }

      // router.refresh() removed - navigation handles data refresh automatically
      return { success: true };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Login failed';
      setError(message);
      return { success: false, error: message };
    } finally {
      setLoading(false);
    }
  };

  const register = async (data: RegisterData) => {
    setLoading(true);
    setError(null);
    try {
      const response = await authService.register(data);
      router.push('/auth/verify-email');
      return { success: true, message: response.message };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Registration failed';
      setError(message);
      return { success: false, error: message };
    } finally {
      setLoading(false);
    }
  };

  const logout = async () => {
    setLoading(true);
    try {
      // Call API first, then clear state only if successful
      await authService.logout();

      // Only clear state if API succeeds
      clearUser();

      router.push('/');
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Logout failed';
      setError(message);
      // User state NOT cleared - they remain logged in on error
    } finally {
      setLoading(false);
    }
  };

  const forgotPassword = async (email: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await authService.forgotPassword({ email });
      return { success: true, message: response.message };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to send reset email';
      setError(message);
      return { success: false, error: message };
    } finally {
      setLoading(false);
    }
  };

  const resetPassword = async (password: string, confirmPassword: string) => {
    setLoading(true);
    setError(null);
    try {
      const response = await authService.resetPassword({ password, confirmPassword });

      // Sync global auth state (reset-password flow creates/updates session via auth callback).
      // This prevents the navbar from showing "Guest" after a successful reset.
      let requiresMFA = false;
      try {
        const me = await authService.getCurrentUser();
        requiresMFA = !!me.requiresMFA;
        setAuthFromLogin({
          user: me.user,
          mfaRequired: requiresMFA,
        });
      } catch {
        // If the session isn't available yet for some reason, still treat password reset as success.
        // GlobalContext can be refreshed later.
      }

      return { success: true, message: response.message, requiresMFA };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to reset password';
      setError(message);
      return { success: false, error: message };
    } finally {
      setLoading(false);
    }
  };

  return { login, register, logout, forgotPassword, resetPassword, loading, error };
}
