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
  logo_url: string | null;
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

/**
 * Upload (or replace) a school's logo.
 *
 * Sends the image as multipart form data to the FastAPI backend, which writes
 * it to Supabase Storage and persists the resulting public URL on the school.
 * Mirrors profileService.uploadAvatar — uses a raw fetch (not apiClient, which
 * is JSON-only) so the browser sets the multipart boundary itself.
 * Returns the updated school (including the new logo_url).
 */
export async function uploadSchoolLogo(
  schoolId: string,
  file: File,
): Promise<School> {
  const formData = new FormData();
  formData.append('file', file);

  const response = await fetch(`/api/v1/admin/schools/${schoolId}/logo`, {
    method: 'POST',
    credentials: 'include',
    body: formData,
  });

  if (!response.ok) {
    const error = await response
      .json()
      .catch(() => ({ error: 'Upload failed' }));
    throw new Error(
      error.detail || error.error || error.message || 'Logo upload failed',
    );
  }

  return response.json();
}
