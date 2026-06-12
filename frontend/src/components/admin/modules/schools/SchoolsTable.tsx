import { CheckCircle, Pencil, XCircle } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { ACTIVE_BADGE_CLASS } from '@/components/admin/statusBadge';
import type { School } from '@/lib/services/schools.service';

interface SchoolsTableProps {
  schools: School[];
  loading: boolean;
  error: string | null;
  canUpdate: boolean;
  onEdit: (school: School) => void;
}

function TableLoadingSkeleton() {
  return (
    <div className="p-8 space-y-4" role="status" aria-label="Loading schools">
      {Array.from({ length: 8 }).map((_, i) => (
        <div key={i} className="h-12 rounded bg-muted animate-pulse" />
      ))}
      <span className="sr-only">Loading schools...</span>
    </div>
  );
}

function ActiveBadge({ isActive }: { isActive: boolean }) {
  return isActive ? (
    <Badge variant="secondary" className={ACTIVE_BADGE_CLASS}>
      <CheckCircle className="h-3 w-3 mr-1" />
      Active
    </Badge>
  ) : (
    <Badge variant="outline" className="w-fit text-muted-foreground">
      <XCircle className="h-3 w-3 mr-1" />
      Inactive
    </Badge>
  );
}

export function SchoolsTable({
  schools,
  loading,
  error,
  canUpdate,
  onEdit,
}: SchoolsTableProps) {
  function renderContent() {
    if (loading) return <TableLoadingSkeleton />;
    if (error) {
      return (
        <div className="p-8 text-center" role="alert">
          <p className="text-sm text-destructive">{error}</p>
        </div>
      );
    }
    if (schools.length === 0) {
      return (
        <div className="p-12 text-center">
          <p className="text-sm font-medium text-muted-foreground">
            No schools found
          </p>
          <p className="text-xs text-muted-foreground mt-1">
            No schools in the system
          </p>
        </div>
      );
    }

    return (
      <div className="overflow-x-auto">
        <Table aria-label="Schools list">
          <TableHeader>
            <TableRow className="bg-muted/40">
              <TableHead scope="col" className="font-semibold">
                Name
              </TableHead>
              <TableHead scope="col" className="font-semibold">
                Short Name
              </TableHead>
              <TableHead scope="col" className="font-semibold">
                Schoology Building ID
              </TableHead>
              <TableHead scope="col" className="font-semibold">
                Current Session
              </TableHead>
              <TableHead scope="col" className="font-semibold">
                Status
              </TableHead>
              {canUpdate && (
                <TableHead scope="col" className="font-semibold w-[50px]">
                  <span className="sr-only">Actions</span>
                </TableHead>
              )}
            </TableRow>
          </TableHeader>
          <TableBody>
            {schools.map((school) => (
              <TableRow key={school.school_id} className="hover:bg-muted/30">
                <TableCell>
                  <p className="font-medium text-sm">{school.name}</p>
                </TableCell>
                <TableCell className="text-sm">{school.short_name}</TableCell>
                <TableCell className="text-sm font-mono text-muted-foreground">
                  {school.schoology_building_id}
                </TableCell>
                <TableCell className="text-sm text-muted-foreground">
                  {school.current_session || '—'}
                </TableCell>
                <TableCell>
                  <ActiveBadge isActive={school.is_active} />
                </TableCell>
                {canUpdate && (
                  <TableCell>
                    <Button
                      variant="ghost"
                      size="icon"
                      className="h-8 w-8"
                      onClick={() => onEdit(school)}
                      aria-label={`Edit ${school.name}`}
                    >
                      <Pencil className="h-4 w-4" />
                    </Button>
                  </TableCell>
                )}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    );
  }

  return (
    <Card className="border-border shadow-sm">
      <CardContent className="p-0">{renderContent()}</CardContent>
    </Card>
  );
}
