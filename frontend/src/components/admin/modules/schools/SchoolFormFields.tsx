'use client';

import type {
  FieldErrors,
  FieldValues,
  Path,
  UseFormRegister,
} from 'react-hook-form';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';

/**
 * Shared field markup for the school create/edit dialogs.
 *
 * Both dialogs render the identical five-field body + `is_active` switch; only
 * the schema (create vs update), service call, titles, and DOM id prefixes
 * differ. Those stay in each dialog — this component owns just the markup.
 *
 * `idPrefix` namespaces the `id`/`htmlFor` pairs ('' for create, 'edit-' for
 * edit) so the two dialogs keep their original element ids verbatim.
 */

// Field names common to SchoolCreateInput and SchoolUpdateInput.
type SchoolFieldName =
  | 'name'
  | 'short_name'
  | 'schoology_building_id'
  | 'schoology_school_id'
  | 'current_session';

interface SchoolFormFieldsProps<T extends FieldValues> {
  register: UseFormRegister<T>;
  errors: FieldErrors<T>;
  isActive: boolean;
  onActiveChange: (checked: boolean) => void;
  /** '' for create, 'edit-' for edit. */
  idPrefix?: string;
}

export default function SchoolFormFields<T extends FieldValues>({
  register,
  errors,
  isActive,
  onActiveChange,
  idPrefix = '',
}: SchoolFormFieldsProps<T>) {
  const field = (name: SchoolFieldName) => name as Path<T>;
  const errorOf = (name: SchoolFieldName) =>
    errors[name as keyof FieldErrors<T>] as { message?: string } | undefined;
  const id = (name: string) => `${idPrefix}${name}`;

  return (
    <div className="space-y-4 py-4">
      <div className="space-y-2">
        <Label htmlFor={id('name')}>Name *</Label>
        <Input
          id={id('name')}
          placeholder="e.g., Springfield High School"
          {...register(field('name'))}
          aria-invalid={!!errorOf('name')}
        />
        {errorOf('name') && (
          <p className="text-sm text-destructive">{errorOf('name')?.message}</p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor={id('short_name')}>Short Name *</Label>
        <Input
          id={id('short_name')}
          placeholder="e.g., SHS"
          {...register(field('short_name'))}
          aria-invalid={!!errorOf('short_name')}
        />
        {errorOf('short_name') && (
          <p className="text-sm text-destructive">
            {errorOf('short_name')?.message}
          </p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor={id('schoology_building_id')}>
          Schoology Building ID *
        </Label>
        <Input
          id={id('schoology_building_id')}
          placeholder="e.g., 1234567890"
          {...register(field('schoology_building_id'))}
          aria-invalid={!!errorOf('schoology_building_id')}
        />
        {errorOf('schoology_building_id') && (
          <p className="text-sm text-destructive">
            {errorOf('schoology_building_id')?.message}
          </p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor={id('schoology_school_id')}>Schoology School ID</Label>
        <Input
          id={id('schoology_school_id')}
          placeholder="Optional"
          {...register(field('schoology_school_id'))}
        />
        {errorOf('schoology_school_id') && (
          <p className="text-sm text-destructive">
            {errorOf('schoology_school_id')?.message}
          </p>
        )}
      </div>

      <div className="space-y-2">
        <Label htmlFor={id('current_session')}>Current Session</Label>
        <Input
          id={id('current_session')}
          placeholder="e.g., 2024-2025"
          {...register(field('current_session'))}
        />
        {errorOf('current_session') && (
          <p className="text-sm text-destructive">
            {errorOf('current_session')?.message}
          </p>
        )}
      </div>

      <div className="flex items-center justify-between rounded-md border border-border p-3">
        <div className="space-y-0.5">
          <Label htmlFor={id('is_active')}>Active</Label>
          <p className="text-xs text-muted-foreground">
            Inactive schools are hidden from report scoping.
          </p>
        </div>
        <Switch
          id={id('is_active')}
          checked={isActive}
          onCheckedChange={onActiveChange}
        />
      </div>
    </div>
  );
}
