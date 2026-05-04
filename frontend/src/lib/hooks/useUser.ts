'use client';

import { useState } from 'react';
import { useRouter } from 'next/navigation';
import { userService } from '@/lib/services/user.service';
import type { UserProfile, UserProfileUpdate, PasswordChangeData } from '@/lib/types/user.types';

export function useUser() {
  const router = useRouter();
  const [profile, setProfile] = useState<UserProfile | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fetchProfile = async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await userService.getProfile();
      setProfile(data);
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to fetch profile';
      setError(message);
    } finally {
      setLoading(false);
    }
  };

  const updateProfile = async (data: UserProfileUpdate) => {
    setLoading(true);
    setError(null);
    try {
      const updated = await userService.updateProfile(data);
      setProfile(updated);
      return { success: true };
    } catch (err) {
      const message = err instanceof Error ? err.message : 'Failed to update profile';
      setError(message);
      return { success: false, error: message };
    } finally {
      setLoading(false);
    }
  };

  const changePassword = async (data: PasswordChangeData) => {
    setLoading(true);
    setError(null);
    try {
      const response = await userService.changePassword(data);
      return { success: true, message: response.message };
    } catch (err: unknown) {
      // Check if error is MFA requirement
      const requiresMFA =
        (typeof err === 'object' && err !== null && 'requiresMFA' in err && (err as { requiresMFA?: boolean }).requiresMFA) ||
        (err instanceof Error && err.message.includes('MFA verification required'));

      if (requiresMFA) {
        router.push('/auth/2fa?returnTo=/app/user-settings');
        return { success: false, error: 'MFA verification required', requiresMFA: true };
      }

      const message = err instanceof Error ? err.message : 'Failed to change password';
      setError(message);
      return { success: false, error: message };
    } finally {
      setLoading(false);
    }
  };

  return { profile, fetchProfile, updateProfile, changePassword, loading, error };
}
