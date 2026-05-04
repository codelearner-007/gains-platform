'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { registerSchema, type RegisterInput } from '@/lib/schemas/auth.schema';
import { getPasswordStrength } from '@/lib/schemas/password.schema';
import { Button } from '@/components/ui/button';
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from '@/components/ui/form';
import { Input } from '@/components/ui/input';
import { cn } from '@/lib/utils';

interface Props {
  onSubmit: (data: RegisterInput) => Promise<{ success: boolean; error?: string; message?: string }>;
  loading?: boolean;
}

export function RegisterForm({ onSubmit, loading }: Props) {
  const [passwordStrength, setPasswordStrength] = useState(0);
  const form = useForm<RegisterInput>({
    resolver: zodResolver(registerSchema),
    defaultValues: {
      email: '',
      password: '',
      confirmPassword: '',
      full_name: '',
    },
  });

  const handleSubmit = async (data: RegisterInput) => {
    const result = await onSubmit(data);
    if (!result.success && result.error) {
      form.setError('root', { message: result.error });
    }
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        {form.formState.errors.root && (
          <div className="text-sm text-destructive">
            {form.formState.errors.root.message}
          </div>
        )}

        <FormField
          control={form.control}
          name="full_name"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Full Name (Optional)</FormLabel>
              <FormControl>
                <Input type="text" placeholder="John Doe" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Email</FormLabel>
              <FormControl>
                <Input type="email" placeholder="you@example.com" autoComplete="email" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <FormField
          control={form.control}
          name="password"
          render={({ field }) => (
            <FormItem>
              <FormLabel>Password</FormLabel>
              <FormControl>
                <Input
                  type="password"
                  autoComplete="new-password"
                  placeholder="Create a strong password"
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
                          'h-2 flex-1 rounded-full transition-colors',
                          level < passwordStrength
                            ? ['bg-destructive', 'bg-chart-1', 'bg-chart-4', 'bg-chart-2', 'bg-chart-5'][passwordStrength] ||
                                'bg-destructive'
                            : 'bg-muted'
                        )}
                      />
                    ))}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Password strength:{' '}
                    <span className="font-medium">
                      {['Very Weak', 'Weak', 'Fair', 'Strong', 'Very Strong'][passwordStrength] || 'Very Weak'}
                    </span>
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
              <FormLabel>Confirm Password</FormLabel>
              <FormControl>
                <Input type="password" autoComplete="new-password" placeholder="Re-enter your password" {...field} />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <Button type="submit" className="w-full" disabled={loading}>
          {loading ? 'Registering...' : 'Register'}
        </Button>
      </form>
    </Form>
  );
}
