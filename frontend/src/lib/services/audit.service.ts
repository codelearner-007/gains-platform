/**
 * Audit Service - API client for audit log management.
 */

import { apiClient } from './api-client';

export interface AuditLog {
  id: string;
  created_at: string;
  user_id: string | null;
  action: string;
  module: string;
  resource_id: string | null;
  details: Record<string, unknown> | null;
}

export interface PaginatedAuditResponse {
  items: AuditLog[];
  total: number;
  page: number;
  page_size: number;
  total_pages: number;
}

export interface AuditLogFilters {
  page: number;
  page_size: number;
  module?: string;
  action?: string;
  user_id?: string;
  start_date?: string;
  end_date?: string;
}

export async function listAuditLogs(params: AuditLogFilters): Promise<PaginatedAuditResponse> {
  const queryString = new URLSearchParams(
    Object.entries(params)
      .filter(([, v]) => v !== undefined && v !== '')
      .map(([k, v]) => [k, String(v)])
  ).toString();

  return apiClient.get<PaginatedAuditResponse>(`/v1/audit/logs?${queryString}`);
}

export async function listAuditModules(): Promise<string[]> {
  return apiClient.get<string[]>('/v1/audit/modules');
}
