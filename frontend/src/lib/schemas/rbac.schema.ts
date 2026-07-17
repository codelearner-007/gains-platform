import { z } from 'zod';

export const roleCreateSchema = z.object({
  name: z
    .string()
    .min(2, 'Role name must be at least 2 characters')
    .max(50, 'Role name must not exceed 50 characters')
    .regex(
      /^[a-z0-9_]+$/,
      'Role name: lowercase letters, numbers and underscores only',
    ),
  description: z
    .string()
    .max(200, 'Description must not exceed 200 characters')
    .optional(),
});

// Seniority is set by drag-and-drop reorder, never by an input on this form.
export const roleUpdateSchema = roleCreateSchema.partial();

// For forms/resolvers, use the INPUT type (defaults make the input optional).
export type RoleCreateInput = z.input<typeof roleCreateSchema>;
export type RoleUpdateInput = z.input<typeof roleUpdateSchema>;
