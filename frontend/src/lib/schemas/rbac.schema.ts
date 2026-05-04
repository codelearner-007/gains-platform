import { z } from 'zod';

export const roleCreateSchema = z.object({
  name: z
    .string()
    .min(2, 'Role name must be at least 2 characters')
    .max(50, 'Role name must not exceed 50 characters')
    .regex(/^[a-z_]+$/, 'Role name must be lowercase with underscores only'),
  description: z
    .string()
    .max(200, 'Description must not exceed 200 characters')
    .optional(),
});

export const roleUpdateSchema = roleCreateSchema
  .extend({
    hierarchy_level: z
      .number()
      .int('Hierarchy level must be an integer')
      .min(0, 'Hierarchy level must be at least 0')
      .max(100000, 'Hierarchy level must not exceed 100,000')
      .optional(),
  })
  .partial();

export const userRoleAssignSchema = z.object({
  role_id: z.string().uuid('Invalid role ID'),
});

export const rolePermissionsUpdateSchema = z.object({
  permission_ids: z
    .array(z.string().uuid('Invalid permission ID'))
    .min(1, 'Must select at least one permission'),
});

// For forms/resolvers, use the INPUT type (defaults make the input optional).
export type RoleCreateInput = z.input<typeof roleCreateSchema>;
export type RoleUpdateInput = z.input<typeof roleUpdateSchema>;
export type UserRoleAssignInput = z.infer<typeof userRoleAssignSchema>;
export type RolePermissionsUpdateInput = z.infer<typeof rolePermissionsUpdateSchema>;
