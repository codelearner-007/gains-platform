import { apiClient } from './api-client';

export interface SessionInfo {
  id: string;
  user_agent: string | null;
  ip: string | null;
  created_at: string;
  updated_at: string | null;
  refreshed_at: string | null;
  is_current: boolean;
}

export interface SessionListResponse {
  sessions: SessionInfo[];
  total: number;
}

export const sessionService = {
  async getSessions(): Promise<SessionListResponse> {
    return apiClient.get<SessionListResponse>('/v1/sessions');
  },

  async revokeSession(sessionId: string): Promise<void> {
    await apiClient.delete(`/v1/sessions/${sessionId}`);
  },
};
