'use client';

import { useState, useEffect, useCallback } from 'react';
import { format } from 'date-fns';
import type { DateRange } from 'react-day-picker';
import {
  ChevronLeft,
  ChevronRight,
  ChevronDown,
  Search,
  Filter,
  Calendar as CalendarIcon,
  Download,
  Ban,
  CheckCircle2,
  Activity,
} from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import { useDebounce } from '@/hooks/useDebounce';
import {
  humanizeAudit,
  auditSeverity,
  type AuditSeverity,
} from '@/lib/audit/humanize';
import {
  listAuditLogs,
  listAuditModules,
  listAuditActions,
  type AuditLog,
  type AuditLogFilters,
} from '@/lib/services/audit.service';

const SEVERITY_STYLE: Record<AuditSeverity, string> = {
  create: 'bg-success/15 text-success',
  update: 'bg-muted text-muted-foreground',
  delete: 'bg-destructive/10 text-destructive',
  neutral: 'bg-muted text-muted-foreground',
};

function SeverityIcon({ action }: { action: string }) {
  const sev = auditSeverity(action);
  const Icon = sev === 'delete' ? Ban : sev === 'create' ? CheckCircle2 : Activity;
  return (
    <div
      className={cn(
        'flex h-7 w-7 shrink-0 items-center justify-center rounded-full',
        SEVERITY_STYLE[sev],
      )}
    >
      <Icon className="h-3.5 w-3.5" />
    </div>
  );
}

export default function AdminAuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [modules, setModules] = useState<string[]>([]);
  const [actions, setActions] = useState<string[]>([]);
  const [dateRange, setDateRange] = useState<DateRange | undefined>();
  const [searchInput, setSearchInput] = useState('');
  const debouncedSearch = useDebounce(searchInput, 300);
  const [filters, setFilters] = useState<AuditLogFilters>({ page: 1, page_size: 50 });
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);
  const [exporting, setExporting] = useState(false);

  useEffect(() => {
    listAuditModules().then(setModules).catch(() => {});
    listAuditActions().then(setActions).catch(() => {});
  }, []);

  useEffect(() => {
    setFilters((prev) => ({ ...prev, q: debouncedSearch || undefined, page: 1 }));
  }, [debouncedSearch]);

  useEffect(() => {
    async function load() {
      try {
        setLoading(true);
        setError(null);
        const res = await listAuditLogs(filters);
        setLogs(res.items);
        setTotalPages(res.total_pages);
        setTotal(res.total);
      } catch (err) {
        setError(err instanceof Error ? err.message : 'Failed to load audit logs');
      } finally {
        setLoading(false);
      }
    }
    load();
  }, [filters]);

  const setFilter = useCallback(
    (key: keyof AuditLogFilters, value: string | undefined) => {
      setFilters((prev) => ({
        ...prev,
        [key]: value === 'all' || value === '' ? undefined : value,
        page: 1,
      }));
    },
    [],
  );

  const handleDateRange = (range: DateRange | undefined) => {
    setDateRange(range);
    setFilters((prev) => {
      const next = { ...prev, page: 1 };
      if (range?.from) next.start_date = range.from.toISOString();
      else delete next.start_date;
      if (range?.to) {
        const end = new Date(range.to);
        end.setHours(23, 59, 59, 999);
        next.end_date = end.toISOString();
      } else delete next.end_date;
      return next;
    });
  };

  const clearAll = () => {
    setDateRange(undefined);
    setSearchInput('');
    setFilters({ page: 1, page_size: filters.page_size });
  };

  const menuCount = [filters.module, filters.action].filter(Boolean).length;

  const exportCsv = async () => {
    setExporting(true);
    try {
      const res = await listAuditLogs({ ...filters, page: 1, page_size: 1000 });
      const header = [
        'timestamp',
        'actor',
        'action',
        'module',
        'resource_id',
        'ip_address',
        'summary',
        'details',
      ];
      const rows = res.items.map((l) => [
        l.created_at,
        l.actor_email ?? l.user_id ?? 'system',
        l.action,
        l.module,
        l.resource_id ?? '',
        l.ip_address ?? '',
        humanizeAudit(l),
        l.details ? JSON.stringify(l.details) : '',
      ]);
      const csv = [header, ...rows]
        .map((r) => r.map((c) => `"${String(c).replace(/"/g, '""')}"`).join(','))
        .join('\n');
      const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' });
      const url = URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `audit-logs-${format(new Date(), 'yyyy-MM-dd')}.csv`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success(`Exported ${res.items.length} rows`);
    } catch {
      toast.error('Export failed');
    } finally {
      setExporting(false);
    }
  };

  return (
    <div className="space-y-6 max-w-[1600px]">
      <div className="flex flex-wrap items-start justify-between gap-4">
        <div>
          <h1 className="text-2xl font-bold text-foreground">Audit Logs</h1>
          <p className="text-sm text-muted-foreground mt-1">
            A human-readable trail of every administrative action.
          </p>
        </div>
        <Button variant="outline" onClick={exportCsv} disabled={exporting || loading}>
          <Download className="h-4 w-4 mr-2" />
          {exporting ? 'Exporting…' : 'Export CSV'}
        </Button>
      </div>

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2">
        <div className="relative min-w-[220px] flex-1 sm:max-w-sm">
          <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-muted-foreground" />
          <Input
            className="pl-9"
            placeholder="Search actions, details…"
            value={searchInput}
            onChange={(e) => setSearchInput(e.target.value)}
            aria-label="Search audit logs"
          />
        </div>

        <Popover>
          <PopoverTrigger asChild>
            <Button variant="outline" className="gap-2">
              <Filter className="h-4 w-4" />
              Filters
              {menuCount > 0 && (
                <Badge className="ml-1 h-5 min-w-5 justify-center rounded-full bg-primary px-1.5 text-primary-foreground tabular-nums">
                  {menuCount}
                </Badge>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent align="end" className="w-72 space-y-4">
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Module</Label>
              <Select
                value={filters.module || 'all'}
                onValueChange={(v) => setFilter('module', v)}
              >
                <SelectTrigger aria-label="Filter by module">
                  <SelectValue placeholder="All modules" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All modules</SelectItem>
                  {modules.map((m) => (
                    <SelectItem key={m} value={m}>
                      {m}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            <div className="space-y-1.5">
              <Label className="text-xs font-medium">Action</Label>
              <Select
                value={filters.action || 'all'}
                onValueChange={(v) => setFilter('action', v)}
              >
                <SelectTrigger aria-label="Filter by action">
                  <SelectValue placeholder="All actions" />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="all">All actions</SelectItem>
                  {actions.map((a) => (
                    <SelectItem key={a} value={a}>
                      {a.replace(/_/g, ' ')}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
            </div>
            {(menuCount > 0 || filters.start_date) && (
              <Button
                variant="ghost"
                size="sm"
                className="w-full text-muted-foreground"
                onClick={clearAll}
              >
                Clear all filters
              </Button>
            )}
          </PopoverContent>
        </Popover>

        {/* Date range — top-level (not nested, to keep Radix useId stable) */}
        <Popover>
          <PopoverTrigger asChild>
            <Button
              variant="outline"
              className={cn('gap-2 font-normal', !dateRange && 'text-muted-foreground')}
            >
              <CalendarIcon className="h-4 w-4" />
              {dateRange?.from ? (
                dateRange.to ? (
                  <>
                    {format(dateRange.from, 'LLL d')} – {format(dateRange.to, 'LLL d, y')}
                  </>
                ) : (
                  format(dateRange.from, 'LLL d, y')
                )
              ) : (
                <span>Any time</span>
              )}
            </Button>
          </PopoverTrigger>
          <PopoverContent className="w-auto p-0" align="end">
            <Calendar
              mode="range"
              defaultMonth={dateRange?.from}
              selected={dateRange}
              onSelect={handleDateRange}
              numberOfMonths={1}
            />
          </PopoverContent>
        </Popover>
      </div>

      {/* Feed */}
      <Card className="border-border shadow-sm">
        <CardContent className="p-0">
          {loading ? (
            <div className="p-6 space-y-3">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-14 rounded bg-muted animate-pulse" />
              ))}
            </div>
          ) : error ? (
            <div className="p-8 text-center text-sm text-destructive">{error}</div>
          ) : logs.length === 0 ? (
            <div className="p-12 text-center">
              <p className="text-sm font-medium text-muted-foreground">
                No audit events found
              </p>
              <p className="text-xs text-muted-foreground mt-1">
                Try adjusting your filters.
              </p>
            </div>
          ) : (
            <>
              <ul className="divide-y divide-border">
                {logs.map((log) => {
                  const isOpen = expanded === log.id;
                  return (
                    <li key={log.id}>
                      <button
                        className="flex w-full items-center gap-3 px-5 py-3 text-left hover:bg-muted/30"
                        onClick={() => setExpanded(isOpen ? null : log.id)}
                        aria-expanded={isOpen}
                      >
                        <SeverityIcon action={log.action} />
                        <div className="min-w-0 flex-1">
                          <p className="text-sm text-foreground">
                            {humanizeAudit(log)}
                          </p>
                          <p className="text-xs text-muted-foreground">
                            {format(new Date(log.created_at), 'MMM d, yyyy · h:mm:ss a')}
                          </p>
                        </div>
                        <Badge
                          variant="secondary"
                          className="hidden sm:inline-flex bg-muted text-muted-foreground font-normal"
                        >
                          {log.module}
                        </Badge>
                        <ChevronDown
                          className={cn(
                            'h-4 w-4 text-muted-foreground transition-transform',
                            isOpen && 'rotate-180',
                          )}
                        />
                      </button>
                      {isOpen && (
                        <div className="border-t border-border bg-muted/20 px-5 py-3 pl-16">
                          <dl className="grid grid-cols-1 gap-x-8 gap-y-2 text-sm sm:grid-cols-2">
                            <DetailRow label="Action" value={log.action} mono />
                            <DetailRow
                              label="Actor"
                              value={log.actor_email ?? log.user_id ?? 'system'}
                            />
                            {log.resource_id && (
                              <DetailRow label="Resource" value={log.resource_id} mono />
                            )}
                            {log.ip_address && (
                              <DetailRow label="IP" value={log.ip_address} mono />
                            )}
                            {log.user_agent && (
                              <DetailRow label="User agent" value={log.user_agent} />
                            )}
                          </dl>
                          {log.details && Object.keys(log.details).length > 0 && (
                            <div className="mt-3">
                              <p className="mb-1 text-xs font-medium text-muted-foreground">
                                Details
                              </p>
                              <pre className="overflow-x-auto rounded-md border border-border bg-card p-3 text-xs">
                                {JSON.stringify(log.details, null, 2)}
                              </pre>
                            </div>
                          )}
                        </div>
                      )}
                    </li>
                  );
                })}
              </ul>

              <div className="flex items-center justify-between border-t border-border bg-muted/20 px-6 py-4">
                <div className="text-sm text-muted-foreground">
                  Showing{' '}
                  <span className="font-medium text-foreground">
                    {(filters.page - 1) * filters.page_size + 1}
                  </span>{' '}
                  –{' '}
                  <span className="font-medium text-foreground">
                    {Math.min(filters.page * filters.page_size, total)}
                  </span>{' '}
                  of <span className="font-medium text-foreground">{total}</span>
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setFilters((p) => ({ ...p, page: p.page - 1 }))
                    }
                    disabled={filters.page === 1 || loading}
                  >
                    <ChevronLeft className="h-4 w-4 mr-1" /> Previous
                  </Button>
                  <span className="px-2 text-sm text-muted-foreground">
                    Page{' '}
                    <span className="font-medium text-foreground">{filters.page}</span>{' '}
                    of{' '}
                    <span className="font-medium text-foreground">{totalPages}</span>
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setFilters((p) => ({ ...p, page: p.page + 1 }))
                    }
                    disabled={filters.page >= totalPages || loading}
                  >
                    Next <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
}

function DetailRow({
  label,
  value,
  mono,
}: {
  label: string;
  value: string;
  mono?: boolean;
}) {
  return (
    <div className="flex gap-2">
      <dt className="w-24 shrink-0 text-muted-foreground">{label}</dt>
      <dd className={cn('min-w-0 break-all text-foreground', mono && 'font-mono text-xs')}>
        {value}
      </dd>
    </div>
  );
}
