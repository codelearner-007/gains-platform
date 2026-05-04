import { ChevronLeft, ChevronRight } from 'lucide-react';
import { Button } from '@/components/ui/button';

interface UserPaginationProps {
  page: number;
  pageSize: number;
  total: number;
  totalPages: number;
  loading: boolean;
  onSetPage: (page: number) => void;
}

export function UserPagination({
  page,
  pageSize,
  total,
  totalPages,
  loading,
  onSetPage,
}: UserPaginationProps) {
  const startIndex = (page - 1) * pageSize + 1;
  const endIndex = Math.min(page * pageSize, total);

  return (
    <nav
      aria-label="Pagination"
      className="flex flex-col sm:flex-row items-center justify-between gap-4 px-6 py-4 border-t border-border bg-muted/20"
    >
      <div className="text-sm text-muted-foreground">
        Showing{' '}
        <span className="font-medium text-foreground">{startIndex}</span> to{' '}
        <span className="font-medium text-foreground">{endIndex}</span> of{' '}
        <span className="font-medium text-foreground">{total}</span> users
      </div>

      <div className="flex items-center gap-2">
        <Button
          variant="outline"
          size="sm"
          onClick={() => onSetPage(page - 1)}
          disabled={page === 1 || loading}
          className="shadow-sm"
          aria-label="Go to previous page"
        >
          <ChevronLeft className="h-4 w-4 mr-1" />
          <span className="hidden sm:inline">Previous</span>
          <span className="sm:hidden">Prev</span>
        </Button>

        <span className="text-sm text-muted-foreground px-2" aria-current="page">
          Page <span className="font-medium text-foreground">{page}</span> of{' '}
          <span className="font-medium text-foreground">{totalPages}</span>
        </span>

        <Button
          variant="outline"
          size="sm"
          onClick={() => onSetPage(page + 1)}
          disabled={page >= totalPages || loading}
          className="shadow-sm"
          aria-label="Go to next page"
        >
          Next
          <ChevronRight className="h-4 w-4 ml-1" />
        </Button>
      </div>
    </nav>
  );
}
