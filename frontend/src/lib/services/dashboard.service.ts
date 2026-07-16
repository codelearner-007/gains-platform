/**
 * Admin overview service — owner-grade stats for /admin.
 */

import { apiClient } from './api-client';

export interface PeopleStats {
  total: number;
  active_7d: number;
  active_30d: number;
  pending_invites: number;
  banned: number;
}

export interface PendingInvite {
  id: string;
  email: string | null;
  invited_at: string | null;
}

export interface RoleDistribution {
  role_id: string;
  name: string;
  hierarchy_level: number;
  users: number;
}

export interface SchoolUserDistribution {
  school_id: string;
  name: string;
  short_name: string | null;
  users: number;
}

export interface SchoolCoverage {
  school_id: string;
  name: string;
  short_name: string | null;
  logo_url: string | null;
  is_active: boolean;
  current_session: string | null;
  assessments: number;
  students: number;
  subjects: number;
  sessions_covered: number;
  last_assessment_date: string | null;
  is_stale: boolean;
}

export interface ActivityEntry {
  id: string;
  created_at: string | null;
  action: string;
  module: string | null;
  resource_id: string | null;
  details: Record<string, unknown> | null;
  actor_email: string | null;
}

export interface IngestionHealth {
  run_id: string | null;
  school_id: string | null;
  status: string | null;
  started_at: string | null;
  finished_at: string | null;
  files_processed: number | null;
  rows_inserted: number | null;
  error_count: number | null;
}

export interface AdminOverview {
  people: PeopleStats;
  pending_invites: PendingInvite[];
  roles: RoleDistribution[];
  schools_users: SchoolUserDistribution[];
  coverage: SchoolCoverage[];
  recent_activity: ActivityEntry[];
  ingestion: IngestionHealth | null;
  generated_at: string;
}

export async function getAdminOverview(): Promise<AdminOverview> {
  return apiClient.get<AdminOverview>('/v1/dashboard/stats');
}
