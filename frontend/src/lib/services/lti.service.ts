/**
 * LTI Service - API client for admin-dynamic LTI 1.3 binding management.
 *
 * Calls FastAPI backend via Next.js rewrites (/api/v1). Admin CRUD lives under
 * /v1/admin/lti (perm: schools:manage_lti). Mirrors schools.service.ts.
 */

import { apiClient } from './api-client';

/** The three tool URLs to hand the district (+ tool kid when bound). */
export interface LtiToolUrls {
  login_init: string;
  launch: string;
  jwks: string;
  tool_kid: string | null;
}

/** A school's resolved binding — never carries the tool private key. */
export interface LtiBinding {
  registration_id: string;
  issuer: string;
  client_id: string;
  platform_name: string | null;
  deployment_id: string;
  is_active: boolean;
  tool_kid: string;
}

/** Binding-or-empty shape the dialog renders. */
export interface LtiSchoolBinding {
  school_id: string;
  bound: boolean;
  binding: LtiBinding | null;
}

/** PUT body — issuer is optional (defaults to Schoology server-side). */
export interface LtiBindingUpsert {
  client_id: string;
  deployment_id: string;
  platform_name?: string;
  is_active: boolean;
  issuer?: string;
}

/** The three tool URLs to copy back to the district. */
export async function getLtiToolUrls(): Promise<LtiToolUrls> {
  return apiClient.get<LtiToolUrls>('/v1/admin/lti/tool-urls');
}

/** Current LTI binding for a school (or empty). */
export async function getSchoolLti(
  schoolId: string,
): Promise<LtiSchoolBinding> {
  return apiClient.get<LtiSchoolBinding>(`/v1/admin/lti/schools/${schoolId}`);
}

/** Create/reuse the registration and (re)bind the school's deployment. */
export async function saveSchoolLti(
  schoolId: string,
  data: LtiBindingUpsert,
): Promise<LtiSchoolBinding> {
  return apiClient.put<LtiSchoolBinding>(
    `/v1/admin/lti/schools/${schoolId}`,
    data,
  );
}

/** Unbind a school (delete its deployment; registration is kept). */
export async function deleteSchoolLti(schoolId: string): Promise<void> {
  await apiClient.delete<void>(`/v1/admin/lti/schools/${schoolId}`);
}
