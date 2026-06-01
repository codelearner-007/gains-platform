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
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import {
  schoolCreateSchema,
  type SchoolCreateInput,
} from '@/lib/schemas/schools.schema';
import { createSchool } from '@/lib/services/schools.service';

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

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="name">Name *</Label>
              <Input
                id="name"
                placeholder="e.g., Springfield High School"
                {...register('name')}
                aria-invalid={!!errors.name}
              />
              {errors.name && (
                <p className="text-sm text-destructive">{errors.name.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="short_name">Short Name *</Label>
              <Input
                id="short_name"
                placeholder="e.g., SHS"
                {...register('short_name')}
                aria-invalid={!!errors.short_name}
              />
              {errors.short_name && (
                <p className="text-sm text-destructive">
                  {errors.short_name.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="schoology_building_id">
                Schoology Building ID *
              </Label>
              <Input
                id="schoology_building_id"
                placeholder="e.g., 1234567890"
                {...register('schoology_building_id')}
                aria-invalid={!!errors.schoology_building_id}
              />
              {errors.schoology_building_id && (
                <p className="text-sm text-destructive">
                  {errors.schoology_building_id.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="schoology_school_id">Schoology School ID</Label>
              <Input
                id="schoology_school_id"
                placeholder="Optional"
                {...register('schoology_school_id')}
              />
              {errors.schoology_school_id && (
                <p className="text-sm text-destructive">
                  {errors.schoology_school_id.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="current_session">Current Session</Label>
              <Input
                id="current_session"
                placeholder="e.g., 2024-2025"
                {...register('current_session')}
              />
              {errors.current_session && (
                <p className="text-sm text-destructive">
                  {errors.current_session.message}
                </p>
              )}
            </div>

            <div className="flex items-center justify-between rounded-md border border-border p-3">
              <div className="space-y-0.5">
                <Label htmlFor="is_active">Active</Label>
                <p className="text-xs text-muted-foreground">
                  Inactive schools are hidden from report scoping.
                </p>
              </div>
              <Switch
                id="is_active"
                checked={isActive}
                onCheckedChange={(checked) => setValue('is_active', checked)}
              />
            </div>
          </div>

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
