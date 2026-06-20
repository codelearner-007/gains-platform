import type { ReactNode } from 'react';

interface ReportCanvasProps {
  children: ReactNode;
}

/**
 * Standard page frame used by every report page (QRA, SDD, YTD, IAD,
 * Standard Summary, Strand Summary).
 *
 * Centers a fixed-max-width canvas with the PBIX-style outer chrome
 * (`#CACEDA` background, drop shadow, 12px padding). Each caller controls
 * its own inter-section spacing via `mb-2` on children — this wrapper
 * is purely the visual frame.
 */
export default function ReportCanvas({ children }: ReportCanvasProps) {
  return (
    <div className="w-full flex justify-center print:block">
      {/* `print:!w-full` overrides the inline 1280px cap so the report fills the
          printable page width (A4 landscape ≈ 1030px) instead of overflowing and
          clipping the right-hand columns; chrome (tint/padding/shadow) is dropped
          for a clean white PDF. */}
      <div
        className="bg-[#CACEDA] p-3 shadow-md print:!w-full print:!bg-white print:!p-0 print:!shadow-none"
        style={{ width: 'min(100%, 1280px)' }}
      >
        {children}
      </div>
    </div>
  );
}
