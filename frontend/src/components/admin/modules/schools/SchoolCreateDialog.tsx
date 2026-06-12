'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, Plus } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { toast } from 'sonner';
import {
  schoolCreateSchema,
  type SchoolCreateInput,
} from '@/lib/schemas/schools.schema';
import { createSchool } from '@/lib/services/schools.service';
import SchoolFormFields from './SchoolFormFields';

interface SchoolCreateDialogProps {
  onSuccess: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

export function SchoolCreateDialog({
  onSuccess,
  open: controlledOpen,
  onOpenChange,
}: SchoolCreateDialogProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);

  const open = controlledOpen ?? internalOpen;
  const setOpen = onOpenChange ?? setInternalOpen;

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
  } = useForm<SchoolCreateInput>({
    resolver: zodResolver(schoolCreateSchema),
    defaultValues: { is_active: true },
  });

  const isActive = watch('is_active') ?? true;

  const onSubmit = async (data: SchoolCreateInput) => {
    try {
      setSubmitting(true);
      const parsed = schoolCreateSchema.parse(data);
      await createSchool(parsed);
      toast('School created', {
        description: `"${parsed.name}" has been created successfully.`,
      });
      setOpen(false);
      reset({ is_active: true });
      onSuccess();
    } catch (err) {
      console.error('Error creating school:', err);
      toast('Failed to create school', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="h-4 w-4 mr-2" />
          Create School
        </Button>
      </DialogTrigger>
      <DialogContent>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogHeader>
            <DialogTitle>Create New School</DialogTitle>
            <DialogDescription>
              Add a new school (tenant). New schools are active by default.
            </DialogDescription>
          </DialogHeader>

          <SchoolFormFields
            register={register}
            errors={errors}
            isActive={isActive}
            onActiveChange={(checked) => setValue('is_active', checked)}
          />

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={() => setOpen(false)}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Create School
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
