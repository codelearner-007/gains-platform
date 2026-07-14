'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface HScrollRowProps {
  children: React.ReactNode;
  /** Accessible label for the scrollable group. */
  ariaLabel?: string;
  /** Gap utility for the row (e.g. "gap-3"). */
  gapClass?: string;
}

/**
 * Single-row horizontal scroller. Content NEVER wraps: when the items fit they
 * are centered; when they overflow, the row scrolls horizontally and left/right
 * arrow controls + edge fades appear so the overflow is discoverable. The native
 * scrollbar is hidden for a clean look, but the region stays scrollable by
 * wheel / trackpad / touch, and the items inside remain keyboard-tabbable
 * (focusing one scrolls it into view natively). Smooth scroll respects
 * prefers-reduced-motion.
 */
export default function HScrollRow({
  children,
  ariaLabel,
  gapClass = 'gap-3',
}: HScrollRowProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [overflow, setOverflow] = useState(false);
  const [canLeft, setCanLeft] = useState(false);
  const [canRight, setCanRight] = useState(false);

  const update = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    const { scrollLeft, scrollWidth, clientWidth } = el;
    setOverflow(scrollWidth - clientWidth > 1);
    setCanLeft(scrollLeft > 1);
    setCanRight(scrollLeft + clientWidth < scrollWidth - 1);
  }, []);

  // Subscribe once: the scroll listener + ResizeObserver keep `update` in sync
  // with scroll position and container size (`update` is stable).
  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.addEventListener('scroll', update, { passive: true });
    const ro = new ResizeObserver(update);
    ro.observe(el);
    return () => {
      el.removeEventListener('scroll', update);
      ro.disconnect();
    };
  }, [update]);

  // Re-measure when the content changes — the observer only catches container
  // resizes, not a change in the number of items.
  useEffect(() => {
    update();
  }, [update, children]);

  const scrollByDir = (dir: -1 | 1) => {
    const el = ref.current;
    if (!el) return;
    el.scrollBy({ left: dir * Math.max(el.clientWidth * 0.8, 240), behavior: 'smooth' });
  };

  const arrowBase =
    'absolute top-1/2 z-20 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-full border border-border bg-card text-foreground shadow-md transition-opacity hover:bg-accent';
  const fadeBase = 'pointer-events-none absolute inset-y-0 z-10 w-12 transition-opacity';

  return (
    <div className="relative">
      {overflow && (
        <>
          <div
            aria-hidden
            className={`${fadeBase} left-0 bg-gradient-to-r from-background to-transparent ${canLeft ? 'opacity-100' : 'opacity-0'}`}
          />
          <button
            type="button"
            aria-label="Scroll left"
            tabIndex={-1}
            onClick={() => scrollByDir(-1)}
            className={`${arrowBase} left-0 ${canLeft ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
          >
            <ChevronLeft className="h-4 w-4" />
          </button>
        </>
      )}

      <div
        ref={ref}
        role="group"
        aria-label={ariaLabel}
        className={`flex ${gapClass} overflow-x-auto px-0.5 py-1 motion-safe:scroll-smooth [scrollbar-width:none] [&::-webkit-scrollbar]:hidden`}
      >
        {children}
      </div>

      {overflow && (
        <>
          <div
            aria-hidden
            className={`${fadeBase} right-0 bg-gradient-to-l from-background to-transparent ${canRight ? 'opacity-100' : 'opacity-0'}`}
          />
          <button
            type="button"
            aria-label="Scroll right"
            tabIndex={-1}
            onClick={() => scrollByDir(1)}
            className={`${arrowBase} right-0 ${canRight ? 'opacity-100' : 'pointer-events-none opacity-0'}`}
          >
            <ChevronRight className="h-4 w-4" />
          </button>
        </>
      )}
    </div>
  );
}
