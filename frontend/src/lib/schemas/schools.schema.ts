import { z } from 'zod';

export const schoolCreateSchema = z.object({
  name: z
    .string()
    .min(2, 'Name must be at least 2 characters')
    .max(200, 'Name must not exceed 200 characters'),
  short_name: z
    .string()
    .min(1, 'Short name is required')
    .max(50, 'Short name must not exceed 50 characters'),
  schoology_building_id: z
    .string()
    .min(1, 'Schoology building ID is required')
    .max(50, 'Schoology building ID must not exceed 50 characters'),
  schoology_school_id: z
    .string()
    .max(50, 'Schoology school ID must not exceed 50 characters')
    .optional(),
  current_session: z
    .string()
    .max(50, 'Current session must not exceed 50 characters')
    .optional(),
  is_active: z.boolean().optional(),
});

export const schoolUpdateSchema = schoolCreateSchema.partial();

// For forms/resolvers, use the INPUT type (optional fields stay optional).
export type SchoolCreateInput = z.input<typeof schoolCreateSchema>;
export type SchoolUpdateInput = z.input<typeof schoolUpdateSchema>;
