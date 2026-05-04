import { apiClient } from './api-client';
import type { UserProfile, UserProfileUpdate, PasswordChangeData } from '@/lib/types/user.types';

export const userService = {
  async getProfile(): Promise<UserProfile> {
    return apiClient.get<UserProfile>('/v1/profile');
  },

  async updateProfile(data: UserProfileUpdate): Promise<UserProfile> {
    return apiClient.patch<UserProfile>('/v1/profile', data);
  },

  async changePassword(data: PasswordChangeData): Promise<{ message: string }> {
    return apiClient.post<{ message: string }>('/auth/change-password', data);
  },
};
