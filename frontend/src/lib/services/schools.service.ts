/**
 * Schools Service - API client for school (tenant) management
 *
 * Calls FastAPI backend via Next.js rewrites (/api/v1).
 * Admin CRUD lives under /v1/admin/schools (perms: schools:read_all,
 * schools:create, schools:update).
 */

import { apiClient } from './api-client';

// Response type matching FastAPI backend
export interface School {
  school_id: string;
  schoology_building_id: string;
  schoology_school_id: string | null;
  name: string;
  short_name: string;
  current_session: string | null;
  timezone: string;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

export interface CreateSchool {
  name: string;
  short_name: string;
  schoology_building_id: string;
  schoology_school_id?: string;
  current_session?: string;
  is_active?: boolean;
}

export interface UpdateSchool {
  name?: string;
  short_name?: string;
  schoology_building_id?: string;
  schoology_school_id?: string;
  current_session?: string;
  is_active?: boolean;
}

/**
 * List all schools
 */
export async function listSchools(): Promise<School[]> {
  return apiClient.get<School[]>('/v1/admin/schools');
}

/**
 * Get a single school by id
 */
export async function getSchool(schoolId: string): Promise<School> {
  return apiClient.get<School>(`/v1/admin/schools/${schoolId}`);
}

/**
 * Create a new school
 */
export async function createSchool(data: CreateSchool): Promise<School> {
  return apiClient.post<School>('/v1/admin/schools', data);
}

/**
 * Update a school
 */
export async function updateSchool(
  schoolId: string,
  data: UpdateSchool,
): Promise<School> {
  return apiClient.put<School>(`/v1/admin/schools/${schoolId}`, data);
}
