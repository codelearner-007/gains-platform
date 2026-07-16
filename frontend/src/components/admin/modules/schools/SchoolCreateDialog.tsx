'use client';

import { useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { Loader2, Plus, ImageIcon, X } from 'lucide-react';
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
import { Label } from '@/components/ui/label';
import { toast } from 'sonner';
import {
  schoolCreateSchema,
  type SchoolCreateInput,
} from '@/lib/schemas/schools.schema';
import { createSchool, uploadSchoolLogo } from '@/lib/services/schools.service';
import SchoolFormFields from './SchoolFormFields';

interface SchoolCreateDialogProps {
  onSuccess: () => void;
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

const LOGO_MAX_BYTES = 2 * 1024 * 1024; // 2MB (matches the backend limit)
const LOGO_TYPES = ['image/jpeg', 'image/png', 'image/webp', 'image/gif'];

export function SchoolCreateDialog({
  onSuccess,
  open: controlledOpen,
  onOpenChange,
}: SchoolCreateDialogProps) {
  const [internalOpen, setInternalOpen] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [logoFile, setLogoFile] = useState<File | null>(null);
  const [logoPreview, setLogoPreview] = useState<string | null>(null);
  const [logoError, setLogoError] = useState<string | null>(null);

  const open = controlledOpen ?? internalOpen;

  const clearLogo = () => {
    setLogoFile(null);
    setLogoError(null);
    if (logoPreview) URL.revokeObjectURL(logoPreview);
    setLogoPreview(null);
  };

  const setOpen = (next: boolean) => {
    if (!next) clearLogo();
    (onOpenChange ?? setInternalOpen)(next);
  };

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

  const onLogoSelect = (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    e.target.value = ''; // allow re-selecting the same file
    if (!file) return;
    if (!LOGO_TYPES.includes(file.type)) {
      setLogoError('Use a JPEG, PNG, WebP or GIF image.');
      return;
    }
    if (file.size > LOGO_MAX_BYTES) {
      setLogoError('Image must be 2MB or smaller.');
      return;
    }
    setLogoError(null);
    if (logoPreview) URL.revokeObjectURL(logoPreview);
    setLogoFile(file);
    setLogoPreview(URL.createObjectURL(file));
  };

  const onSubmit = async (data: SchoolCreateInput) => {
    try {
      setSubmitting(true);
      const parsed = schoolCreateSchema.parse(data);
      const created = await createSchool(parsed);

      // Optional logo: upload after creation. A logo failure does NOT undo the
      // school (it can be added later from Manage) — surface it as a warning.
      if (logoFile) {
        try {
          await uploadSchoolLogo(created.school_id, logoFile);
        } catch {
          toast.warning('School created, but the logo failed to upload', {
            description: 'You can add it later from Manage.',
          });
        }
      }

      toast.success('School created', {
        description: `"${parsed.name}" has been created.`,
      });
      setOpen(false);
      reset({ is_active: true });
      onSuccess();
    } catch (err) {
      console.error('Error creating school:', err);
      toast.error('Failed to create school', {
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

          {/* Optional logo */}
          <div className="space-y-2 pt-4">
            <Label>Logo (optional)</Label>
            <div className="flex items-center gap-4">
              {logoPreview ? (
                // eslint-disable-next-line @next/next/no-img-element
                <img
                  src={logoPreview}
                  alt="Logo preview"
                  className="h-16 w-16 rounded-lg border border-border object-contain bg-card"
                />
              ) : (
                <div className="flex h-16 w-16 items-center justify-center rounded-lg border border-dashed border-border bg-muted text-muted-foreground">
                  <ImageIcon className="h-5 w-5" />
                </div>
              )}
              <div className="space-y-1">
                <div className="flex gap-2">
                  <Button type="button" variant="outline" size="sm" asChild>
                    <label className="cursor-pointer">
                      {logoFile ? 'Change' : 'Choose image'}
                      <input
                        type="file"
                        accept={LOGO_TYPES.join(',')}
                        className="sr-only"
                        onChange={onLogoSelect}
                      />
                    </label>
                  </Button>
                  {logoFile && (
                    <Button
                      type="button"
                      variant="ghost"
                      size="sm"
                      onClick={clearLogo}
                    >
                      <X className="h-3.5 w-3.5 mr-1" /> Remove
                    </Button>
                  )}
                </div>
                <p className="text-xs text-muted-foreground">
                  JPEG, PNG, WebP or GIF · max 2MB
                </p>
              </div>
            </div>
            {logoError && <p className="text-sm text-destructive">{logoError}</p>}
          </div>

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
