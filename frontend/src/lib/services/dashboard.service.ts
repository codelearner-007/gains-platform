/**
 * Dashboard Service - admin dashboard statistics.
 */

import type { DashboardStats } from '@/lib/types/dashboard';
import { apiClient } from './api-client';

export type { DashboardStats };

export async function getDashboardStats(): Promise<DashboardStats> {
  return apiClient.get<DashboardStats>('/v1/dashboard/stats');
}
