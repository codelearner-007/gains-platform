'use client';

import Link from 'next/link';
import { usePathname, useSearchParams } from 'next/navigation';
import { useEffect, useState } from 'react';
import { BarChart3, FileBarChart, Layers, LineChart } from 'lucide-react';

const ITEM_ID_STORAGE_KEY = 'gains.lastItemId';

const items = [
  {
    name: 'All Reports',
    href: '/app/reports',
    icon: BarChart3,
    requiresItem: false,
  },
  {
    name: 'Question Response Analysis',
    href: '/app/reports/question-response-analysis',
    icon: FileBarChart,
    requiresItem: true,
  },
  {
    name: 'Standards Deep Dive',
    href: '/app/reports/standards-deep-dive',
    icon: Layers,
    requiresItem: true,
  },
  {
    name: 'Year-To-Date Performance',
    href: '/app/reports/year-to-date-performance',
    icon: LineChart,
    requiresItem: false,
  },
];

export default function ReportsNav() {
  const pathname = usePathname();
  const searchParams = useSearchParams();
  const itemIdFromUrl = searchParams.get('item_id');
  const [rememberedItemId, setRememberedItemId] = useState<string | null>(null);

  // On mount, hydrate from sessionStorage so YTD/landing remember the last assessment
  useEffect(() => {
    if (typeof window === 'undefined') return;
    const stored = window.sessionStorage.getItem(ITEM_ID_STORAGE_KEY);
    if (stored) setRememberedItemId(stored);
  }, []);

  // Whenever URL has an item_id, persist it
  useEffect(() => {
    if (typeof window === 'undefined') return;
    if (itemIdFromUrl) {
      window.sessionStorage.setItem(ITEM_ID_STORAGE_KEY, itemIdFromUrl);
      setRememberedItemId(itemIdFromUrl);
    }
  }, [itemIdFromUrl]);

  const effectiveItemId = itemIdFromUrl ?? rememberedItemId;

  return (
    <nav className="flex flex-wrap items-center gap-1 border-b border-border pb-2 mb-4">
      {items.map((item) => {
        const Icon = item.icon;
        const active =
          pathname === item.href ||
          (item.href !== '/app/reports' && pathname.startsWith(item.href));
        const href =
          item.requiresItem && effectiveItemId
            ? { pathname: item.href, query: { item_id: effectiveItemId } }
            : item.href;
        // Per-assessment tabs link to the landing page when no item is known yet
        const targetHref =
          item.requiresItem && !effectiveItemId ? '/app/reports' : href;
        return (
          <Link
            key={item.href}
            href={targetHref}
            title={
              item.requiresItem && !effectiveItemId
                ? 'Pick an assessment first'
                : undefined
            }
            className={`flex items-center gap-2 px-3 py-1.5 text-sm rounded-md transition-colors ${
              active
                ? 'bg-primary-soft text-primary'
                : 'text-muted-foreground hover:bg-accent hover:text-foreground'
            }`}
          >
            <Icon className="h-3.5 w-3.5" />
            {item.name}
          </Link>
        );
      })}
    </nav>
  );
}
