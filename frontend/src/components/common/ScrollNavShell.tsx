'use client';

import { useEffect, useState } from 'react';
import { cn } from '@/lib/utils';

/**
 * Wraps the nav's inner row and widens it toward the viewport edges once the
 * page has scrolled — the logo and CTA "shift to extreme sides" as a cue that
 * you've moved past the hero. Threshold matches the hero's rough scroll-past
 * point rather than firing on the first pixel of scroll.
 */
export function ScrollNavShell({ children }: { children: React.ReactNode }) {
  const [scrolled, setScrolled] = useState(false);

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 24);
    onScroll();
    window.addEventListener('scroll', onScroll, { passive: true });
    return () => window.removeEventListener('scroll', onScroll);
  }, []);

  return (
    <div
      className={cn(
        'mx-auto transition-[max-width,padding] duration-500 ease-out',
        scrolled ? 'max-w-full px-4 sm:px-6 lg:px-10' : 'max-w-7xl px-4 sm:px-6 lg:px-8'
      )}
    >
      {children}
    </div>
  );
}
