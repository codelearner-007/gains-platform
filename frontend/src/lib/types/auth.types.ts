import type { PermissionString } from './rbac.types';

export interface LoginCredentials {
  email: string;
  password: string;
}

export interface RegisterData {
  email: string;
  password: string;
  confirmPassword: string;
  full_name?: string;
}

/**
 * Safe auth response shape - tokens are never exposed in the response body.
 * Session tokens are managed exclusively via httpOnly cookies by Supabase SSR.
 */
export interface AuthResponse {
  user: {
    id: string;
    email?: string;
    user_metadata: Record<string, unknown>;
    app_metadata: Record<string, unknown>;
  } | null;
  error?: string;
  requiresMFA?: boolean;
  currentAAL?: 'aal1' | 'aal2';
}

export interface UserMetadata {
  full_name?: string;
  avatar_url?: string;
  [key: string]: unknown;
}

export interface AppMetadata {
  user_role?: string;
  hierarchy_level?: number;
  permissions?: PermissionString[];
  [key: string]: unknown;
}

export interface CurrentUser {
  id: string;
  email: string | null;
  user_metadata?: UserMetadata;
  app_metadata?: AppMetadata;
  created_at: string;
}

export interface CurrentUserResponse {
  user: CurrentUser | null;
  requiresMFA?: boolean;
  currentAAL?: 'aal1' | 'aal2';
}

export interface MFASetupData {
  factor_id: string;
  code: string;
}

export interface MFAVerifyData {
  factor_id: string;
  code: string;
}

export interface ForgotPasswordData {
  email: string;
}

export interface ResetPasswordData {
  password: string;
  confirmPassword: string;
}

export interface MFAStatusResponse {
  currentLevel: 'aal1' | 'aal2';
  nextLevel: 'aal1' | 'aal2';
}

export interface MFAFactor {
  id: string;
  friendly_name: string;
  factor_type: 'totp' | 'phone';
  status: 'verified' | 'unverified';
}

export interface MFAFactorListItem {
  id: string;
  status: string;
  friendly_name?: string | null;
  factor_type?: string;
  created_at: string;
}

export interface MFAFactorsResponse {
  all: MFAFactorListItem[];
  totp: MFAFactorListItem[];
  phone?: MFAFactorListItem[]; // Optional - not all projects enable phone MFA
}
