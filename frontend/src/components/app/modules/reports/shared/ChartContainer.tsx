'use client';

import { useEffect, useRef, useState, type CSSProperties, type ReactElement } from 'react';
import { ResponsiveContainer } from 'recharts';

interface ChartContainerProps {
  /**
   * The recharts chart element (BarChart, Treemap, etc.). Rendered inside a
   * `ResponsiveContainer` once the wrapper has a measured non-zero size.
   */
  children: ReactElement;
  /** Wrapper height — a fixed px number or `'100%'` to fill the parent. */
  height?: number | string;
  className?: string;
  style?: CSSProperties;
}

/**
 * Measured wrapper around recharts' `ResponsiveContainer`.
 *
 * recharts logs `The width(-1) and height(-1) of chart should be greater than
 * 0` when `ResponsiveContainer` mounts before the DOM has laid the parent out
 * (its initial measurement reads -1). We defer mounting the chart until a
 * `ResizeObserver` reports a positive width/height, then hand `ResponsiveContainer`
 * the measured pixel dimensions so it never measures a non-positive size.
 */
export default function ChartContainer({
  children,
  height = '100%',
  className,
  style,
}: ChartContainerProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [size, setSize] = useState<{ width: number; height: number } | null>(
    null,
  );

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    const observer = new ResizeObserver((entries) => {
      const entry = entries[0];
      if (!entry) return;
      const { width, height: h } = entry.contentRect;
      if (width > 0 && h > 0) {
        setSize((prev) =>
          prev && prev.width === width && prev.height === h
            ? prev
            : { width, height: h },
        );
      }
    });
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  return (
    <div ref={ref} className={className} style={{ height, ...style }}>
      {size ? (
        <ResponsiveContainer width={size.width} height={size.height}>
          {children}
        </ResponsiveContainer>
      ) : null}
    </div>
  );
}
