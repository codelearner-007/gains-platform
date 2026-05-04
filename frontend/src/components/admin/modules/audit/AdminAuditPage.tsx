'use client';

/**
 * Admin Audit Logs Page
 *
 * Professional audit trail with advanced filtering using calendar range picker
 */

import { useState, useEffect } from 'react';
import { format } from 'date-fns';
import type { DateRange } from 'react-day-picker';
import { ChevronLeft, ChevronRight, X, Calendar as CalendarIcon, Filter } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Label } from '@/components/ui/label';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from '@/components/ui/table';
import { Popover, PopoverContent, PopoverTrigger } from '@/components/ui/popover';
import { Calendar } from '@/components/ui/calendar';
import { toast } from 'sonner';
import { cn } from '@/lib/utils';
import {
  listAuditLogs,
  listAuditModules,
  type AuditLog,
  type AuditLogFilters,
} from '@/lib/services/audit.service';

export default function AdminAuditPage() {
  const [logs, setLogs] = useState<AuditLog[]>([]);
  const [modules, setModules] = useState<string[]>([]);
  const [dateRange, setDateRange] = useState<DateRange | undefined>();
  const [filters, setFilters] = useState<AuditLogFilters>({
    page: 1,
    page_size: 50,
  });
  const [totalPages, setTotalPages] = useState(1);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingModules, setLoadingModules] = useState(true);
  const [error, setError] = useState<string | null>(null);

  // Load modules for filter dropdown
  useEffect(() => {
    async function loadModules() {
      try {
        setLoadingModules(true);
        const data = await listAuditModules();
        setModules(data);
      } catch (err) {
        console.error('Failed to load modules:', err);
      } finally {
        setLoadingModules(false);
      }
    }

    loadModules();
  }, []);

  // Load logs when filters change
  useEffect(() => {
    async function loadLogs() {
      try {
        setLoading(true);
        setError(null);

        const response = await listAuditLogs(filters);

        setLogs(response.items);
        setTotalPages(response.total_pages);
        setTotal(response.total);
      } catch (err) {
        console.error('Error loading audit logs:', err);
        setError(err instanceof Error ? err.message : 'Failed to load audit logs');
        toast('Failed to load audit logs', {
          description: 'Please try again.',
        });
      } finally {
        setLoading(false);
      }
    }

    loadLogs();
  }, [filters]);

  const formatDate = (dateString: string) => {
    const date = new Date(dateString);
    return new Intl.DateTimeFormat('en-US', {
      month: 'short',
      day: 'numeric',
      year: 'numeric',
      hour: '2-digit',
      minute: '2-digit',
      second: '2-digit',
    }).format(date);
  };

  const formatUserId = (userId: string | null) => {
    if (!userId) return 'System';
    return userId.slice(0, 8);
  };

  const handleDateRangeChange = (range: DateRange | undefined) => {
    setDateRange(range);

    // Update filters with new date range
    const newFilters: AuditLogFilters = {
      ...filters,
      page: 1, // Reset to first page
    };

    if (range?.from) {
      newFilters.start_date = range.from.toISOString();
    } else {
      delete newFilters.start_date;
    }

    if (range?.to) {
      // Set to end of day
      const endOfDay = new Date(range.to);
      endOfDay.setHours(23, 59, 59, 999);
      newFilters.end_date = endOfDay.toISOString();
    } else {
      delete newFilters.end_date;
    }

    setFilters(newFilters);
  };

  const handleModuleChange = (value: string) => {
    setFilters((prev) => ({
      ...prev,
      module: value === 'all' ? undefined : value,
      page: 1,
    }));
  };

  const handleRemoveFilter = (key: keyof AuditLogFilters) => {
    if (key === 'start_date' || key === 'end_date') {
      // Clear entire date range
      setDateRange(undefined);
      setFilters((prev) => {
        const newFilters = { ...prev };
        delete newFilters.start_date;
        delete newFilters.end_date;
        return { ...newFilters, page: 1 };
      });
    } else {
      setFilters((prev) => {
        const newFilters = { ...prev };
        delete newFilters[key];
        return { ...newFilters, page: 1 };
      });
    }
  };

  const handleClearAllFilters = () => {
    setDateRange(undefined);
    setFilters({
      page: 1,
      page_size: filters.page_size,
    });
  };

  const activeFilters = Object.entries(filters).filter(
    ([key, value]) =>
      value !== undefined &&
      key !== 'page' &&
      key !== 'page_size' &&
      value !== ''
  );

  const hasActiveFilters = activeFilters.length > 0;

  return (
    <div className="space-y-6 max-w-[1600px]">
      {/* Header */}
      <div>
        <h1 className="text-2xl font-bold text-foreground">Audit Logs</h1>
        <p className="text-sm text-muted-foreground mt-1">
          Track all system actions and security events
        </p>
      </div>

      {/* Filters */}
      <Card className="border-border shadow-sm">
        <CardContent className="pt-6">
          <div className="space-y-5">
            {/* Filter Controls */}
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {/* Date Range Picker */}
              <div className="space-y-2">
                <Label className="text-sm font-medium">Date Range</Label>
                <Popover>
                  <PopoverTrigger asChild>
                    <Button
                      variant="outline"
                      className={cn(
                        'w-full justify-start text-left font-normal',
                        !dateRange && 'text-muted-foreground'
                      )}
                    >
                      <CalendarIcon className="mr-2 h-4 w-4" />
                      {dateRange?.from ? (
                        dateRange.to ? (
                          <>
                            {format(dateRange.from, 'LLL dd, y')} -{' '}
                            {format(dateRange.to, 'LLL dd, y')}
                          </>
                        ) : (
                          format(dateRange.from, 'LLL dd, y')
                        )
                      ) : (
                        <span>Pick a date range</span>
                      )}
                    </Button>
                  </PopoverTrigger>
                  <PopoverContent className="w-auto p-0" align="start">
                    <Calendar
                      initialFocus
                      mode="range"
                      defaultMonth={dateRange?.from}
                      selected={dateRange}
                      onSelect={handleDateRangeChange}
                      numberOfMonths={2}
                    />
                  </PopoverContent>
                </Popover>
              </div>

              {/* Module Filter */}
              <div className="space-y-2">
                <Label htmlFor="module" className="text-sm font-medium">
                  Module
                </Label>
                <Select
                  value={filters.module || 'all'}
                  onValueChange={handleModuleChange}
                  disabled={loadingModules}
                >
                  <SelectTrigger id="module">
                    <div className="flex items-center gap-2">
                      <Filter className="h-4 w-4 text-muted-foreground" />
                      <SelectValue placeholder="All Modules" />
                    </div>
                  </SelectTrigger>
                  <SelectContent>
                    <SelectItem value="all">All Modules</SelectItem>
                    {modules.map((module) => (
                      <SelectItem key={module} value={module}>
                        {module}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
            </div>

            {/* Active Filters */}
            {hasActiveFilters && (
              <div className="flex items-center gap-3 pt-2 border-t border-border">
                <span className="text-xs font-semibold text-muted-foreground uppercase tracking-wider">
                  Active Filters:
                </span>
                <div className="flex items-center gap-2 flex-wrap">
                  {activeFilters.map(([key, value]) => {
                    let displayValue = String(value);
                    let displayKey = key;

                    // Skip end_date if both dates exist (we show it with start_date as a range)
                    if (key === 'end_date' && dateRange?.from && dateRange?.to) {
                      return null;
                    }

                    // Format display names
                    if (key === 'start_date' && dateRange?.from && dateRange?.to) {
                      displayValue = `${format(dateRange.from, 'MMM d, yyyy')} - ${format(dateRange.to, 'MMM d, yyyy')}`;
                      displayKey = 'Date Range';
                    } else if (key === 'start_date') {
                      displayValue = format(new Date(value as string), 'MMM d, yyyy');
                      displayKey = 'From';
                    } else if (key === 'end_date') {
                      displayValue = format(new Date(value as string), 'MMM d, yyyy');
                      displayKey = 'To';
                    } else if (key === 'module') {
                      displayKey = 'Module';
                    }

                    return (
                      <Badge
                        key={key}
                        variant="secondary"
                        className="gap-2 pl-3 pr-2 py-1.5 bg-primary/10 text-primary border-primary/20 hover:bg-primary/20"
                      >
                        <span className="text-xs font-medium">
                          {displayKey}: {displayValue}
                        </span>
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleRemoveFilter(key as keyof AuditLogFilters)}
                          className="h-5 w-5 hover:bg-primary/20 rounded-full p-0.5 transition-colors"
                          aria-label={`Remove ${key} filter`}
                        >
                          <X className="h-3 w-3" />
                        </Button>
                      </Badge>
                    );
                  })}
                  <div className="flex items-center gap-2">
                    <span className="text-muted-foreground">|</span>
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={handleClearAllFilters}
                      className="h-7 px-2 text-xs font-medium hover:bg-destructive/10 hover:text-destructive"
                    >
                      Clear All
                    </Button>
                  </div>
                </div>
              </div>
            )}
          </div>
        </CardContent>
      </Card>

      {/* Audit Logs Table */}
      <Card className="border-border shadow-sm">
        <CardContent className="p-0">
          {loading ? (
            <div className="p-8 space-y-4">
              {Array.from({ length: 8 }).map((_, i) => (
                <div key={i} className="h-12 rounded bg-muted animate-pulse" />
              ))}
            </div>
          ) : error ? (
            <div className="p-8 text-center">
              <p className="text-sm text-destructive">{error}</p>
            </div>
          ) : logs.length === 0 ? (
            <div className="p-12 text-center">
              <p className="text-sm font-medium text-muted-foreground">No audit logs found</p>
              <p className="text-xs text-muted-foreground mt-1">
                {hasActiveFilters
                  ? 'Try adjusting your filters'
                  : 'No events have been recorded yet'}
              </p>
            </div>
          ) : (
            <>
              <div className="overflow-x-auto">
                <Table>
                  <TableHeader>
                    <TableRow className="bg-muted/40">
                      <TableHead className="font-semibold">Timestamp</TableHead>
                      <TableHead className="font-semibold">Module</TableHead>
                      <TableHead className="font-semibold">Action</TableHead>
                      <TableHead className="font-semibold">User</TableHead>
                      <TableHead className="font-semibold">Resource</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {logs.map((log) => (
                      <TableRow key={log.id} className="hover:bg-muted/30">
                        <TableCell className="text-sm text-muted-foreground font-mono">
                          {formatDate(log.created_at)}
                        </TableCell>
                        <TableCell>
                          <Badge
                            variant="secondary"
                            className="bg-primary/10 text-primary border-primary/20 font-medium"
                          >
                            {log.module}
                          </Badge>
                        </TableCell>
                        <TableCell className="font-medium text-sm">{log.action}</TableCell>
                        <TableCell className="text-sm text-muted-foreground font-mono">
                          {formatUserId(log.user_id)}
                        </TableCell>
                        <TableCell className="text-sm text-muted-foreground">
                          {log.resource_id ? (
                            <code className="bg-muted px-2 py-1 rounded text-xs">
                              {log.resource_id.slice(0, 12)}
                            </code>
                          ) : (
                            <span className="text-muted-foreground/60">—</span>
                          )}
                        </TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between px-6 py-4 border-t border-border bg-muted/20">
                <div className="text-sm text-muted-foreground">
                  Showing{' '}
                  <span className="font-medium text-foreground">
                    {(filters.page - 1) * filters.page_size + 1}
                  </span>{' '}
                  to{' '}
                  <span className="font-medium text-foreground">
                    {Math.min(filters.page * filters.page_size, total)}
                  </span>{' '}
                  of <span className="font-medium text-foreground">{total}</span> events
                </div>
                <div className="flex items-center gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setFilters((prev) => ({ ...prev, page: prev.page - 1 }))
                    }
                    disabled={filters.page === 1 || loading}
                    className="shadow-sm"
                  >
                    <ChevronLeft className="h-4 w-4 mr-1" />
                    Previous
                  </Button>
                  <span className="text-sm text-muted-foreground px-2">
                    Page <span className="font-medium text-foreground">{filters.page}</span> of{' '}
                    <span className="font-medium text-foreground">{totalPages}</span>
                  </span>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() =>
                      setFilters((prev) => ({ ...prev, page: prev.page + 1 }))
                    }
                    disabled={filters.page >= totalPages || loading}
                    className="shadow-sm"
                  >
                    Next
                    <ChevronRight className="h-4 w-4 ml-1" />
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
