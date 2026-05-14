'use client';

import Link from 'next/link';
import { ArrowLeft } from 'lucide-react';

interface Props {
  itemId: string;
}

/**
 * Drill-back-up link from the IAD page to the QRA page that originated
 * the drill-through. Mirrors the action button in the PBIX layout
 * (visual #16 — small chevron icon button at the top-left).
 */
export default function BackToQraLink({ itemId }: Props) {
  return (
    <Link
      href={{
        pathname: '/app/reports/question-response-analysis',
        query: { item_id: itemId },
      }}
      className="inline-flex items-center gap-1.5 px-2.5 py-1 text-xs rounded-md text-muted-foreground hover:bg-accent hover:text-foreground transition-colors"
    >
      <ArrowLeft className="h-3.5 w-3.5" />
      Back to Question Response Analysis
    </Link>
  );
}
