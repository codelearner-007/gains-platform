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
    <div className="w-full flex justify-center">
      <div
        className="bg-[#CACEDA] p-3 shadow-md"
        style={{ width: 'min(100%, 1280px)' }}
      >
        {children}
      </div>
    </div>
  );
}
