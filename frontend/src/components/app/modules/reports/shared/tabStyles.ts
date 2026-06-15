/**
 * Shared tab pill styling for the report navigation toggles
 * (ReportTypeSwitcher inline tabs + ReportVariantTabs sub-toggle).
 *
 * `TAB_BASE` is the layout-agnostic pill base. ReportTypeSwitcher's inline
 * tabs additionally prepend `inline-flex items-center gap-1.5` because they
 * render a leading icon; the variant tabs are plain links and use it as-is.
 * The active/inactive state strings are identical across both consumers.
 */
export const TAB_BASE =
  'px-3 py-1.5 text-sm rounded transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring';
export const TAB_ACTIVE = 'bg-card text-primary shadow-sm font-medium';
export const TAB_INACTIVE =
  'text-muted-foreground hover:bg-accent hover:text-foreground';
