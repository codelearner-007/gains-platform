'use client';

import { Loader2, Search, X } from 'lucide-react';
import { Input } from '@/components/ui/input';

interface SearchInputProps {
  value: string;
  onChange: (next: string) => void;
  loading?: boolean;
  resultCount?: number;
  placeholder?: string;
  className?: string;
}

/**
 * Compact, minimal assessment search. The trailing spinner shows while the
 * (debounced) server query is in flight; an aria-live region announces the
 * result count to screen readers. Debouncing is owned by the parent — it
 * debounces `value` before it reaches the query key — so this input stays
 * instant and fully controlled.
 */
export default function SearchInput({
  value,
  onChange,
  loading,
  resultCount,
  placeholder = 'Search assessments…',
  className,
}: SearchInputProps) {
  return (
    <div className={['relative w-full sm:w-56', className ?? ''].join(' ')}>
      <Search
        className="pointer-events-none absolute left-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground"
        aria-hidden
      />
      <Input
        type="text"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        aria-label="Search assessments by name"
        className="h-9 pl-8 pr-8"
      />
      <span className="absolute right-2.5 top-1/2 -translate-y-1/2">
        {loading ? (
          <Loader2 className="h-4 w-4 animate-spin text-muted-foreground" aria-hidden />
        ) : value ? (
          <button
            type="button"
            onClick={() => onChange('')}
            aria-label="Clear search"
            className="text-muted-foreground transition-colors hover:text-foreground"
          >
            <X className="h-4 w-4" />
          </button>
        ) : null}
      </span>
      <span aria-live="polite" className="sr-only">
        {resultCount == null
          ? ''
          : value
            ? `${resultCount} ${resultCount === 1 ? 'result' : 'results'}`
            : 'Showing all assessments'}
      </span>
    </div>
  );
}
