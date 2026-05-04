'use client';

import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { z } from 'zod';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Form, FormControl, FormField, FormItem, FormMessage } from '@/components/ui/form';

const resendVerificationSchema = z.object({
  email: z.string().email('Please enter a valid email address'),
});

type ResendVerificationInput = z.infer<typeof resendVerificationSchema>;

interface ResendVerificationFormProps {
  onSubmit: (data: ResendVerificationInput) => Promise<void>;
  loading?: boolean;
}

export function ResendVerificationForm({ onSubmit, loading }: ResendVerificationFormProps) {
  const form = useForm<ResendVerificationInput>({
    resolver: zodResolver(resendVerificationSchema),
    defaultValues: {
      email: '',
    },
  });

  const handleSubmit = async (data: ResendVerificationInput) => {
    await onSubmit(data);
  };

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(handleSubmit)} className="space-y-4">
        <FormField
          control={form.control}
          name="email"
          render={({ field }) => (
            <FormItem>
              <FormControl>
                <Input
                  type="email"
                  placeholder="Enter your email address"
                  {...field}
                />
              </FormControl>
              <FormMessage />
            </FormItem>
          )}
        />

        <Button
          type="submit"
          disabled={loading}
          variant="outline"
          className="w-full"
        >
          {loading ? 'Sending...' : 'Resend verification email'}
        </Button>
      </form>
    </Form>
  );
}
