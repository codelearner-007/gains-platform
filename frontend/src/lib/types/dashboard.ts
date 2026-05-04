/**
 * Dashboard types -- TypeScript interfaces for admin dashboard API response.
 *
 * Matches the FastAPI backend DashboardStatsResponse schema.
 */

export interface DashboardStats {
  total_roles: number;
  total_permissions: number;
  total_users: number;
  total_audit_logs: number;
  recent_activity_24h: number;
}
