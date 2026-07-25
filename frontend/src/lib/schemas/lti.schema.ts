import { z } from 'zod';

/**
 * LTI binding form schema. Mirrors the backend LtiBindingUpsertRequest: the
 * admin pastes the district's client_id + deployment_id; issuer + platform
 * URLs default to Schoology server-side, so issuer is optional here.
 */
export const ltiBindingSchema = z.object({
  client_id: z
    .string()
    .min(1, 'Client ID is required')
    .max(255, 'Client ID must not exceed 255 characters'),
  deployment_id: z
    .string()
    .min(1, 'Deployment ID is required')
    .max(255, 'Deployment ID must not exceed 255 characters'),
  platform_name: z
    .string()
    .max(100, 'Platform name must not exceed 100 characters')
    .optional(),
  is_active: z.boolean(),
  issuer: z
    .string()
    .max(255, 'Issuer must not exceed 255 characters')
    .optional(),
});

// For forms/resolvers, use the INPUT type (optional fields stay optional).
export type LtiBindingInput = z.input<typeof ltiBindingSchema>;
