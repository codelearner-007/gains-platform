'use client';

import { useState } from 'react';
import { Download, FileSpreadsheet, FileText, Loader2, Printer } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from '@/components/ui/tooltip';
import {
  buildCsvFilename,
  downloadCsv,
  reportToCsv,
  type ReportKind,
  type ReportPayloadByKind,
} from '@/lib/reports/export-csv';

interface ExportMenuProps<K extends ReportKind> {
  kind: K;
  /** Already-fetched react-query payload (undefined until loaded). */
  payload: ReportPayloadByKind[K] | undefined;
  /** Item name / program label used in the download filename. */
  name?: string | null;
}

type Busy = 'csv' | 'pdf' | null;

/**
 * Shared report export control: a shadcn DropdownMenu with CSV / XLSX / PDF.
 * Mounted once in the report chrome row, so it appears on every report.
 *
 * - CSV: client-side flatten of the cached payload (`export-csv.ts`).
 * - PDF: `window.print()` (Phase 1 — relies on the print stylesheet).
 * - XLSX: disabled with a tooltip until the backend route lands.
 *
 * Always `print:hidden` so it never appears in printed / PDF output. Items
 * stay disabled until the payload is available.
 */
export default function ExportMenu<K extends ReportKind>({
  kind,
  payload,
  name,
}: ExportMenuProps<K>) {
  const [busy, setBusy] = useState<Busy>(null);
  const ready = payload !== undefined;

  function handleCsv() {
    if (!payload) return;
    setBusy('csv');
    try {
      const csv = reportToCsv(kind, payload);
      downloadCsv(csv, buildCsvFilename(kind, name));
    } catch (err) {
      console.error('[export csv]', err);
      toast('Could not export CSV', {
        description:
          err instanceof Error ? err.message : 'Unexpected error building the CSV.',
      });
    } finally {
      setBusy(null);
    }
  }

  function handlePdf() {
    if (!payload) return;
    setBusy('pdf');
    try {
      window.print();
    } catch (err) {
      console.error('[export pdf]', err);
      toast('Could not open the print dialog', {
        description:
          err instanceof Error ? err.message : 'Unexpected error invoking print.',
      });
    } finally {
      setBusy(null);
    }
  }

  return (
    <DropdownMenu>
      <DropdownMenuTrigger asChild>
        <Button
          type="button"
          variant="outline"
          size="sm"
          disabled={!ready}
          className="print:hidden gap-1.5"
        >
          <Download className="h-3.5 w-3.5" />
          Export
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="print:hidden w-44">
        <DropdownMenuItem
          disabled={!ready || busy !== null}
          onSelect={(e) => {
            e.preventDefault();
            handleCsv();
          }}
        >
          {busy === 'csv' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <FileText className="h-3.5 w-3.5" />
          )}
          CSV
        </DropdownMenuItem>

        <TooltipProvider>
          <Tooltip>
            <TooltipTrigger asChild>
              {/* Wrapper span so the tooltip still fires on the disabled item. */}
              <span className="block">
                <DropdownMenuItem disabled aria-disabled className="opacity-50">
                  <FileSpreadsheet className="h-3.5 w-3.5" />
                  XLSX
                </DropdownMenuItem>
              </span>
            </TooltipTrigger>
            <TooltipContent side="left">XLSX coming</TooltipContent>
          </Tooltip>
        </TooltipProvider>

        <DropdownMenuItem
          disabled={!ready || busy !== null}
          onSelect={(e) => {
            e.preventDefault();
            handlePdf();
          }}
        >
          {busy === 'pdf' ? (
            <Loader2 className="h-3.5 w-3.5 animate-spin" />
          ) : (
            <Printer className="h-3.5 w-3.5" />
          )}
          PDF
        </DropdownMenuItem>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
