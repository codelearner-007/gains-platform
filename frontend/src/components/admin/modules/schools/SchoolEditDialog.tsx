'use client';

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import {
  schoolUpdateSchema,
  type SchoolUpdateInput,
} from '@/lib/schemas/schools.schema';
import { updateSchool, type School } from '@/lib/services/schools.service';

interface SchoolEditDialogProps {
  school: School | null;
  onClose: () => void;
  onSuccess: () => void;
}

export function SchoolEditDialog({
  school,
  onClose,
  onSuccess,
}: SchoolEditDialogProps) {
  const [submitting, setSubmitting] = useState(false);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
  } = useForm<SchoolUpdateInput>({
    resolver: zodResolver(schoolUpdateSchema),
  });

  useEffect(() => {
    if (school) {
      reset({
        name: school.name,
        short_name: school.short_name,
        schoology_building_id: school.schoology_building_id,
        schoology_school_id: school.schoology_school_id ?? '',
        current_session: school.current_session ?? '',
        is_active: school.is_active,
      });
    }
  }, [school, reset]);

  const isActive = watch('is_active') ?? true;

  const onSubmit = async (data: SchoolUpdateInput) => {
    if (!school) return;
    try {
      setSubmitting(true);
      await updateSchool(school.school_id, data);
      toast('School updated', {
        description: `"${data.name || school.name}" has been updated successfully.`,
      });
      onSuccess();
      onClose();
    } catch (err) {
      console.error('Error updating school:', err);
      toast('Failed to update school', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <Dialog open={!!school} onOpenChange={(open) => !open && onClose()}>
      <DialogContent>
        <form onSubmit={handleSubmit(onSubmit)}>
          <DialogHeader>
            <DialogTitle>Edit School</DialogTitle>
            <DialogDescription>Update school details.</DialogDescription>
          </DialogHeader>

          <div className="space-y-4 py-4">
            <div className="space-y-2">
              <Label htmlFor="edit-name">Name *</Label>
              <Input
                id="edit-name"
                placeholder="e.g., Springfield High School"
                {...register('name')}
                aria-invalid={!!errors.name}
              />
              {errors.name && (
                <p className="text-sm text-destructive">{errors.name.message}</p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="edit-short_name">Short Name *</Label>
              <Input
                id="edit-short_name"
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
              <Label htmlFor="edit-schoology_building_id">
                Schoology Building ID *
              </Label>
              <Input
                id="edit-schoology_building_id"
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
              <Label htmlFor="edit-schoology_school_id">
                Schoology School ID
              </Label>
              <Input
                id="edit-schoology_school_id"
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
              <Label htmlFor="edit-current_session">Current Session</Label>
              <Input
                id="edit-current_session"
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
                <Label htmlFor="edit-is_active">Active</Label>
                <p className="text-xs text-muted-foreground">
                  Inactive schools are hidden from report scoping.
                </p>
              </div>
              <Switch
                id="edit-is_active"
                checked={isActive}
                onCheckedChange={(checked) => setValue('is_active', checked)}
              />
            </div>
          </div>

          <DialogFooter>
            <Button
              type="button"
              variant="outline"
              onClick={onClose}
              disabled={submitting}
            >
              Cancel
            </Button>
            <Button type="submit" disabled={submitting}>
              {submitting && <Loader2 className="h-4 w-4 mr-2 animate-spin" />}
              Update School
            </Button>
          </DialogFooter>
        </form>
      </DialogContent>
    </Dialog>
  );
}
