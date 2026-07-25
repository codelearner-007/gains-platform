'use client';

import { useEffect, useState } from 'react';
import { useForm } from 'react-hook-form';
import { zodResolver } from '@hookform/resolvers/zod';
import { ChevronDown, Loader2 } from 'lucide-react';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { toast } from 'sonner';
import { ltiBindingSchema, type LtiBindingInput } from '@/lib/schemas/lti.schema';
import {
  deleteSchoolLti,
  getSchoolLti,
  saveSchoolLti,
  type LtiBinding,
} from '@/lib/services/lti.service';
import type { School } from '@/lib/services/schools.service';
import { LtiToolUrls } from './LtiToolUrls';

interface SchoolLTIDialogProps {
  school: School | null;
  onClose: () => void;
}

// The four Schoology platform URLs are fixed defaults — shown, read-only, under
// the Advanced disclosure. The backend owns them; they are informational here.
const SCHOOLOGY_PLATFORM_URLS = [
  { label: 'Issuer', value: 'https://schoology.schoology.com' },
  {
    label: 'Authorize (Login) URL',
    value:
      'https://lti-service.svc.schoology.com/lti-service/authorize-redirect',
  },
  {
    label: 'Access Token URL',
    value: 'https://lti-service.svc.schoology.com/lti-service/access-token',
  },
  {
    label: 'Platform JWKS URL',
    value:
      'https://lti-service.svc.schoology.com/lti-service/.well-known/jwks',
  },
];

export function SchoolLTIDialog({ school, onClose }: SchoolLTIDialogProps) {
  const [loading, setLoading] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [advancedOpen, setAdvancedOpen] = useState(false);
  const [confirmUnbind, setConfirmUnbind] = useState(false);
  const [binding, setBinding] = useState<LtiBinding | null>(null);

  const {
    register,
    handleSubmit,
    formState: { errors },
    reset,
    watch,
    setValue,
  } = useForm<LtiBindingInput>({
    resolver: zodResolver(ltiBindingSchema),
    defaultValues: { client_id: '', deployment_id: '', is_active: true },
  });

  // Load the current binding whenever a school is opened.
  useEffect(() => {
    if (!school) return;
    let active = true;
    setLoading(true);
    setBinding(null);
    getSchoolLti(school.school_id)
      .then((data) => {
        if (!active) return;
        setBinding(data.binding);
        reset({
          client_id: data.binding?.client_id ?? '',
          deployment_id: data.binding?.deployment_id ?? '',
          platform_name: data.binding?.platform_name ?? '',
          is_active: data.binding?.is_active ?? true,
        });
      })
      .catch((err) => {
        if (!active) return;
        toast('Failed to load LTI binding', {
          description: err instanceof Error ? err.message : 'Please try again.',
        });
      })
      .finally(() => {
        if (active) setLoading(false);
      });
    return () => {
      active = false;
    };
  }, [school, reset]);

  const isActive = watch('is_active') ?? true;

  const onSubmit = async (data: LtiBindingInput) => {
    if (!school) return;
    try {
      setSubmitting(true);
      const result = await saveSchoolLti(school.school_id, {
        client_id: data.client_id,
        deployment_id: data.deployment_id,
        platform_name: data.platform_name || undefined,
        is_active: data.is_active,
      });
      setBinding(result.binding);
      toast('LTI binding saved', {
        description: `"${school.name}" is now bound to its Schoology deployment.`,
      });
    } catch (err) {
      toast('Failed to save LTI binding', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setSubmitting(false);
    }
  };

  const onUnbind = async () => {
    if (!school) return;
    try {
      setSubmitting(true);
      await deleteSchoolLti(school.school_id);
      setBinding(null);
      reset({ client_id: '', deployment_id: '', platform_name: '', is_active: true });
      toast('LTI binding removed', {
        description: `"${school.name}" is no longer bound.`,
      });
    } catch (err) {
      toast('Failed to remove LTI binding', {
        description: err instanceof Error ? err.message : 'Please try again.',
      });
    } finally {
      setSubmitting(false);
      setConfirmUnbind(false);
    }
  };

  return (
    <Dialog open={!!school} onOpenChange={(open) => !open && onClose()}>
      <DialogContent className="max-h-[85vh] overflow-y-auto">
        <DialogHeader>
          <DialogTitle>LTI 1.3 Configuration</DialogTitle>
          <DialogDescription>
            Bind {school?.name ?? 'this school'} to its Schoology deployment.
          </DialogDescription>
        </DialogHeader>

        {loading ? (
          <div className="flex items-center gap-2 py-6 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading current binding…
          </div>
        ) : (
          <form onSubmit={handleSubmit(onSubmit)} className="space-y-4">
            {/* Editable binding zone */}
            <div className="space-y-2">
              <Label htmlFor="lti-client-id">Client ID</Label>
              <Input
                id="lti-client-id"
                placeholder="Paste the district's Schoology client_id"
                {...register('client_id')}
              />
              {errors.client_id && (
                <p className="text-sm text-destructive">
                  {errors.client_id.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="lti-deployment-id">Deployment ID</Label>
              <Input
                id="lti-deployment-id"
                placeholder="Paste the deployment_id"
                {...register('deployment_id')}
              />
              {errors.deployment_id && (
                <p className="text-sm text-destructive">
                  {errors.deployment_id.message}
                </p>
              )}
            </div>

            <div className="space-y-2">
              <Label htmlFor="lti-platform-name">Platform Name (optional)</Label>
              <Input
                id="lti-platform-name"
                placeholder="Schoology"
                {...register('platform_name')}
              />
            </div>

            <div className="flex items-center justify-between rounded-md border border-border p-3">
              <div className="space-y-0.5">
                <Label htmlFor="lti-is-active">Enabled</Label>
                <p className="text-xs text-muted-foreground">
                  When disabled, launches for this school fail closed.
                </p>
              </div>
              <Switch
                id="lti-is-active"
                checked={isActive}
                onCheckedChange={(checked) => setValue('is_active', checked)}
              />
            </div>

            {/* Advanced disclosure — the fixed Schoology platform URLs */}
            <div className="rounded-md border border-border">
              <button
                type="button"
                onClick={() => setAdvancedOpen((v) => !v)}
                className="flex w-full items-center justify-between px-3 py-2 text-sm font-medium text-foreground"
                aria-expanded={advancedOpen}
              >
                Advanced — Schoology platform URLs
                <ChevronDown
                  className={`h-4 w-4 text-muted-foreground transition-transform ${
                    advancedOpen ? 'rotate-180' : ''
                  }`}
                />
              </button>
              {advancedOpen && (
                <div className="space-y-2 border-t border-border p-3">
                  {SCHOOLOGY_PLATFORM_URLS.map((u) => (
                    <div key={u.label} className="space-y-0.5">
                      <Label className="text-xs text-muted-foreground">
                        {u.label}
                      </Label>
                      <code className="block truncate rounded-md border border-border bg-muted px-2 py-1.5 text-xs text-foreground">
                        {u.value}
                      </code>
                    </div>
                  ))}
                  <p className="text-xs text-muted-foreground">
                    These are fixed for Schoology and applied automatically.
                  </p>
                </div>
              )}
            </div>

            {/* Tool URLs to hand the district */}
            <div className="space-y-2">
              <Label className="text-sm font-medium text-foreground">
                Tool URLs for the district
              </Label>
              <LtiToolUrls toolKid={binding?.tool_kid} />
            </div>

            <DialogFooter className="gap-2 sm:justify-between">
              <Button
                type="button"
                variant="outline"
                className="text-destructive"
                onClick={() => setConfirmUnbind(true)}
                disabled={submitting || !binding}
              >
                Unbind
              </Button>
              <div className="flex gap-2">
                <Button
                  type="button"
                  variant="outline"
                  onClick={onClose}
                  disabled={submitting}
                >
                  Cancel
                </Button>
                <Button type="submit" disabled={submitting}>
                  {submitting && (
                    <Loader2 className="h-4 w-4 mr-2 animate-spin" />
                  )}
                  Save Binding
                </Button>
              </div>
            </DialogFooter>
          </form>
        )}
      </DialogContent>

      <AlertDialog open={confirmUnbind} onOpenChange={setConfirmUnbind}>
        <AlertDialogContent>
          <AlertDialogHeader>
            <AlertDialogTitle>Remove LTI binding?</AlertDialogTitle>
            <AlertDialogDescription>
              This deletes the deployment binding for {school?.name}. Existing
              launches for this school will stop resolving until it is rebound.
            </AlertDialogDescription>
          </AlertDialogHeader>
          <AlertDialogFooter>
            <AlertDialogCancel disabled={submitting}>Cancel</AlertDialogCancel>
            <AlertDialogAction
              onClick={(e) => {
                e.preventDefault();
                void onUnbind();
              }}
              disabled={submitting}
            >
              Unbind
            </AlertDialogAction>
          </AlertDialogFooter>
        </AlertDialogContent>
      </AlertDialog>
    </Dialog>
  );
}
