import { z } from 'zod';
import { getPasswordStrength, strongPasswordSchema } from '@/lib/schemas/password.schema';

export const userProfileSchema = z.object({
  full_name: z.string().min(1, 'Name is required').optional(),
  avatar_url: z.string().url('Invalid URL').optional().or(z.literal('')),
  department: z.string().optional(),
});

export const passwordChangeSchema = z.object({
  currentPassword: z.string().min(1, 'Current password is required'),
  newPassword: strongPasswordSchema,
  confirmPassword: z.string(),
}).refine((data) => data.newPassword === data.confirmPassword, {
  message: "Passwords don't match",
  path: ['confirmPassword'],
}).refine((data) => data.currentPassword !== data.newPassword, {
  message: "New password must be different from current password",
  path: ['newPassword'],
});

export { getPasswordStrength };

export type UserProfileInput = z.infer<typeof userProfileSchema>;
export type PasswordChangeInput = z.infer<typeof passwordChangeSchema>;
