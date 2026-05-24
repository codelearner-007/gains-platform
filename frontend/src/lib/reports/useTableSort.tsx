'use client';

import { useMemo, useState } from 'react';

export type SortDirection = 'asc' | 'desc';

export type SortAccessor<T> = (row: T) => string | number | null | undefined;

export interface SortConfig<T, K extends string> {
  rows: T[];
  /**
   * Map of column key → accessor. Define once at module scope and pass the
   * same reference each render — re-allocating per render makes the memo
   * deps churn and re-sorts the table on every parent re-render.
   */
  accessors: Record<K, SortAccessor<T>>;
  defaultColumn: K;
  defaultDirection?: SortDirection;
  /** First-click direction per column. `desc` for numeric columns reads as
   *  "show me the highest first"; defaults to `asc` if unspecified. */
  initialDirections?: Partial<Record<K, SortDirection>>;
}

export interface SortResult<T, K extends string> {
  sortedRows: T[];
  sortColumn: K;
  sortDirection: SortDirection;
  onHeaderClick: (column: K) => void;
}

export function useTableSort<T, K extends string>({
  rows,
  accessors,
  defaultColumn,
  defaultDirection = 'asc',
  initialDirections,
}: SortConfig<T, K>): SortResult<T, K> {
  const [sortColumn, setSortColumn] = useState<K>(defaultColumn);
  const [sortDirection, setSortDirection] =
    useState<SortDirection>(defaultDirection);

  const onHeaderClick = (column: K) => {
    if (column === sortColumn) {
      setSortDirection((d) => (d === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortColumn(column);
      setSortDirection(initialDirections?.[column] ?? 'asc');
    }
  };

  const sortedRows = useMemo(() => {
    const accessor = accessors[sortColumn];
    const factor = sortDirection === 'asc' ? 1 : -1;
    const copy = [...rows];
    copy.sort((a, b) => {
      const av = accessor(a);
      const bv = accessor(b);
      // Nulls last regardless of direction (legacy PBIX `NULLS LAST`).
      if (av == null && bv == null) return 0;
      if (av == null) return 1;
      if (bv == null) return -1;
      if (typeof av === 'number' && typeof bv === 'number') {
        return (av - bv) * factor;
      }
      return String(av).localeCompare(String(bv)) * factor;
    });
    return copy;
  }, [rows, accessors, sortColumn, sortDirection]);

  return { sortedRows, sortColumn, sortDirection, onHeaderClick };
}

/**
 * Up/down arrow indicator. Active column shows the current direction;
 * inactive columns show a dimmed up-down chevron pair so the user knows
 * the column is sortable.
 */
export function SortIndicator({
  active,
  direction,
}: {
  active: boolean;
  direction: SortDirection;
}) {
  if (!active) {
    return (
      <span
        aria-hidden
        className="inline-block ml-1 text-[10px] text-neutral-400 leading-none select-none"
      >
        ↕
      </span>
    );
  }
  return (
    <span
      aria-hidden
      className="inline-block ml-1 text-[10px] text-black leading-none select-none"
    >
      {direction === 'asc' ? '▲' : '▼'}
    </span>
  );
}

/**
 * Convenience: a sortable header cell. Renders a button-styled th content
 * that calls back when clicked.
 */
export function SortableHeader<K extends string>({
  column,
  label,
  sortColumn,
  sortDirection,
  onClick,
  className,
  align = 'left',
}: {
  column: K;
  label: string;
  sortColumn: K;
  sortDirection: SortDirection;
  onClick: (col: K) => void;
  className?: string;
  align?: 'left' | 'center' | 'right';
}) {
  const active = column === sortColumn;
  const alignCls =
    align === 'center'
      ? 'justify-center text-center'
      : align === 'right'
        ? 'justify-end text-right'
        : 'justify-start text-left';
  return (
    <button
      type="button"
      onClick={() => onClick(column)}
      aria-sort={
        active ? (sortDirection === 'asc' ? 'ascending' : 'descending') : 'none'
      }
      className={`flex items-center gap-1 w-full select-none cursor-pointer hover:text-neutral-900 ${alignCls} ${
        className ?? ''
      }`}
    >
      <span className="truncate">{label}</span>
      <SortIndicator active={active} direction={sortDirection} />
    </button>
  );
}
