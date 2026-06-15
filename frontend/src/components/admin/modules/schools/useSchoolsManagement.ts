'use client';

import { useCallback, useEffect, useState } from 'react';
import { toast } from 'sonner';
import { useAdminClaims } from '@/components/admin/AdminClaimsContext';
import { hasPermission } from '@/lib/utils/rbac';
import { listSchools, type School } from '@/lib/services/schools.service';

export function useSchoolsManagement() {
  const [schools, setSchools] = useState<School[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Dialog state
  const [createOpen, setCreateOpen] = useState(false);
  const [editSchool, setEditSchool] = useState<School | null>(null);

  // Permission checks
  const claims = useAdminClaims();
  const canCreate = hasPermission(claims.permissions, 'schools:create');
  const canUpdate = hasPermission(claims.permissions, 'schools:update');

  const loadSchools = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await listSchools();
      setSchools(data);
    } catch (err) {
      const message =
        err instanceof Error ? err.message : 'Failed to load schools';
      setError(message);
      toast.error('Failed to load schools', { description: 'Please try again.' });
      console.error('Error loading schools:', err);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void loadSchools();
  }, [loadSchools]);

  return {
    // Data
    schools,
    total: schools.length,

    // Loading
    loading,
    error,

    // Permissions
    canCreate,
    canUpdate,

    // Dialogs
    createOpen,
    setCreateOpen,
    editSchool,
    setEditSchool,

    // Actions
    reload: loadSchools,
  };
}
