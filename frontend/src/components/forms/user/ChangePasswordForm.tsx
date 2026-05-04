'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Form, FormControl, FormDescription, FormField, FormItem, FormLabel, FormMessage } from '@/components/ui/form';
import { passwordChangeSchema, type PasswordChangeInput, getPasswordStrength } from '@/lib/schemas/user.schema';
import { cn } from '@/lib/utils';

interface ChangePasswordFormProps {
  onSubmit: (data: PasswordChangeInput) => Promise<void | { success: boolean; error?: string }>;
  loading?: boolean;
}

export function ChangePasswordForm({ onSubmit, loading }: ChangePasswordFormProps) {
  const [passwordStrength, setPasswordStrength] = useState(0);

  const form = useForm<PasswordChangeInput>({
    resolver: zodResolver(passwordChangeSchema),
    defaultValues: {
      currentPassword: '',
      newPassword: '',
      confirmPassword: '',
    },
  });

  const handleSubmit = async (data: PasswordChangeInput) => {
    const result = await onSubmit(data);
    if (result?.success) {
      form.reset();
      setPasswordStrength(0);
    }
  };

  const getStrengthLabel = (strength: number) => {
    const labels = ['Very Weak', 'Weak', 'Fair', 'Strong', 'Very Strong'];
    return labels[strength] || 'Very Weak';
  };

  const getStrengthColor = (strength: number) => {
    const colors = [
      'bg-destructive',
      'bg-chart-1',
      'bg-chart-4',
      'bg-chart-2',
      'bg-chart-5',
    ];
    return colors[strength] || 'bg-destructive';
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="currentPassword"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Current Password</FormLabel>
              <FormControl>
                <Input
                  type="password"
                  autoComplete="current-password"
                  placeholder="Enter your current password"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="newPassword"
          render={({ field }) => (
            <FormItem>
              <FormLabel>New Password</FormLabel>
              <FormControl>
                <Input
                  type="password"
                  autoComplete="new-password"
                  placeholder="Enter your new password"
                  {...field}
                  onChange={(e) => {
                    field.onChange(e);
                    setPasswordStrength(getPasswordStrength(e.target.value));
                  }}
                />
              </FormControl>
              {field.value && (
                <div className="space-y-2 mt-2">
                  <div className="flex gap-1">
                    {[0, 1, 2, 3, 4].map((level) => (
                      <div
                        key={level}
                        className={cn(
                          "h-2 flex-1 rounded-full transition-colors",
                          level < passwordStrength
                            ? getStrengthColor(passwordStrength)
                            : "bg-muted"
                        )}
                      />
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Password strength: <span className="font-medium">{getStrengthLabel(passwordStrength)}</span>
                  </p>
                </div>
              )}
              <FormDescription>
                Must contain at least 8 characters, including uppercase, lowercase, number, and special character
              </FormDescription>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="confirmPassword"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Confirm New Password</FormLabel>
              <FormControl>
                <Input
                  type="password"
                  autoComplete="new-password"
                  placeholder="Confirm your new password"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <Button type="submit" disabled={loading}>
          {loading ? 'Updating...' : 'Update Password'}
        </Button>
      </form>
    </Form>
  );
}
