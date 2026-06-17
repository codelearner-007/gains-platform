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
import { toast } from 'sonner';
import {
  schoolUpdateSchema,
  type SchoolUpdateInput,
} from '@/lib/schemas/schools.schema';
import { updateSchool, type School } from '@/lib/services/schools.service';
import SchoolFormFields from './SchoolFormFields';
import { SchoolLogoUpload } from './SchoolLogoUpload';

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

          {school && (
            <div className="space-y-2 py-2">
              <label className="text-sm font-medium text-foreground">
                School Logo
              </label>
              <SchoolLogoUpload
                schoolId={school.school_id}
                currentLogoUrl={school.logo_url}
                onUploaded={() => {
                  toast('Logo updated', {
                    description: 'The school logo has been uploaded.',
                  });
                  onSuccess();
                }}
              />
            </div>
          )}

          <SchoolFormFields
            register={register}
            errors={errors}
            isActive={isActive}
            onActiveChange={(checked) => setValue('is_active', checked)}
            idPrefix="edit-"
          />

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
