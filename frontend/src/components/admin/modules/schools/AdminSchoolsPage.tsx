'use client';

import { useSchoolsManagement } from './useSchoolsManagement';
import { SchoolsTable } from './SchoolsTable';
import { SchoolCreateDialog } from './SchoolCreateDialog';
import { SchoolEditDialog } from './SchoolEditDialog';

export default function AdminSchoolsPage() {
  const {
    schools,
    total,
    loading,
    error,
    canCreate,
    canUpdate,
    createOpen,
    setCreateOpen,
    editSchool,
    setEditSchool,
    reload,
  } = useSchoolsManagement();

  return (
    <div className="space-y-6 max-w-[1600px]">
      {/* Header */}
      <div className="flex items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Schools</h1>
          <p className="text-sm text-muted-foreground mt-1">
            Manage schools (tenants)
            {!loading && (
              <span className="ml-1">
                · {total} {total === 1 ? 'school' : 'schools'}
              </span>
            )}
          </p>
        </div>
        {canCreate && (
          <SchoolCreateDialog
            open={createOpen}
            onOpenChange={setCreateOpen}
            onSuccess={reload}
          />
        )}
      </div>

      {/* Table */}
      <SchoolsTable
        schools={schools}
        loading={loading}
        error={error}
        canUpdate={canUpdate}
        onEdit={setEditSchool}
      />

      {/* Edit Dialog */}
      <SchoolEditDialog
        school={editSchool}
        onClose={() => setEditSchool(null)}
        onSuccess={reload}
      />
    </div>
  );
}
