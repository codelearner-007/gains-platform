import { apiClient } from './api-client';

interface ProfileResponse {
  id: string;
  user_id: string;
  full_name: string | null;
  avatar_url: string | null;
  department: string | null;
  timezone: string | null;
  preferences: Record<string, unknown> | null;
  created_at: string;
  updated_at: string;
}

interface UpdatePreferencesData {
  timezone?: string;
  preferences?: Record<string, unknown>;
}

export const profileService = {
  async uploadAvatar(file: File): Promise<{ avatar_url: string }> {
    const formData = new FormData();
    formData.append('file', file);

    const response = await fetch('/api/v1/profile/avatar', {
      method: 'POST',
      credentials: 'include',
      body: formData,
    });

    if (!response.ok) {
      const error = await response.json().catch(() => ({ error: 'Upload failed' }));
      throw new Error(error.error || error.message || 'Avatar upload failed');
    }

    return response.json();
  },

  async updatePreferences(data: UpdatePreferencesData): Promise<ProfileResponse> {
    return apiClient.patch<ProfileResponse>('/v1/profile', data);
  },

  async getProfile(): Promise<ProfileResponse> {
    return apiClient.get<ProfileResponse>('/v1/profile');
  },
};

export type { ProfileResponse, UpdatePreferencesData };
