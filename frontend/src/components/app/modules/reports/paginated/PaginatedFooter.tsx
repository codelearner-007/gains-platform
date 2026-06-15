/**
 * "Generated at … UTC" footer rendered only on print. Browsers don't expose
 * page numbers to the DOM; if pixel-perfect "Page N of M" is needed later,
 * generate the PDF server-side (Playwright / WeasyPrint) — putting a
 * placeholder span here was misleading because CSS Paged Media counters
 * can only write into `@page` margin boxes, not arbitrary elements.
 */
export default function PaginatedFooter() {
  const ts = new Date().toISOString().replace('T', ' ').split('.')[0];
  return (
    <div className="hidden print:block text-[10px] text-neutral-600 px-2 py-1 mt-2 border-t border-neutral-300">
      Generated at {ts} UTC
    </div>
  );
}
