'use client';

import { useCallback, useEffect, useRef, useState } from 'react';
import dynamic from 'next/dynamic';
import 'yet-another-react-lightbox-lite/styles.css';

const Lightbox = dynamic(() => import('yet-another-react-lightbox-lite'), {
  ssr: false,
});

interface RichReportHtmlProps {
  html: string;
  className?: string;
  skeletonLabel?: string;
}

interface ZoomedSlide {
  src: string;
  alt?: string;
}

const IMAGE_LOAD_TIMEOUT_MS = 12000;

/**
 * Renders sanitized report HTML that may contain Schoology images / LaTeX SVGs.
 * The HTML MUST be sanitized upstream — see `lib/reports/format.ts` which
 * uses `sanitize-html` with an allow-list of tags and attributes before this
 * component renders the result via `dangerouslySetInnerHTML`.
 *
 * Responsibilities:
 *   1. Show a per-image shimmer skeleton while images load; replace broken
 *      ones with a readable fallback instead of a browser glyph.
 *   2. Preserve intrinsic aspect ratio. We copy `naturalWidth`/`naturalHeight`
 *      to the `width`/`height` attributes once known so the browser reserves
 *      the correct box (no CLS) and avoids sub-pixel resampling blur.
 *   3. Make every report image click-to-zoom via
 *      `yet-another-react-lightbox-lite` (~5 KB gz, dynamic-imported so it
 *      stays out of the SSR payload). Keyboard accessible (Enter / Space
 *      open; Escape closes).
 */
export default function RichReportHtml({
  html,
  className,
  skeletonLabel = 'Loading report image…',
}: RichReportHtmlProps) {
  const ref = useRef<HTMLDivElement>(null);
  const [isLoadingImages, setIsLoadingImages] = useState(() =>
    /<img\b/i.test(html),
  );
  const [zoomed, setZoomed] = useState<ZoomedSlide | null>(null);

  useEffect(() => {
    const root = ref.current;
    if (!root) return;

    const imgs = Array.from(root.querySelectorAll('img'));
    let remaining = 0;
    let isMounted = true;
    const cleanupFns: Array<() => void> = [];

    const recordIntrinsic = (img: HTMLImageElement) => {
      if (img.naturalWidth && img.naturalHeight) {
        img.setAttribute('width', String(img.naturalWidth));
        img.setAttribute('height', String(img.naturalHeight));
      }
    };

    const markDone = (img: HTMLImageElement) => {
      recordIntrinsic(img);
      if (!img.classList.contains('report-image-loading')) return;
      img.classList.remove('report-image-loading');
      img.removeAttribute('aria-busy');
      remaining -= 1;
      if (remaining <= 0 && isMounted) setIsLoadingImages(false);
    };

    const markBroken = (img: HTMLImageElement) => {
      markDone(img);
      const fallback = document.createElement('span');
      fallback.className = 'report-image-fallback';
      fallback.textContent = '[image unavailable]';
      fallback.setAttribute('role', 'img');
      fallback.setAttribute('aria-label', img.alt || 'report image unavailable');
      img.replaceWith(fallback);
    };

    imgs.forEach((img) => {
      // Wire each image as a zoom trigger for keyboard / screen-reader users.
      // Click is handled by the delegated handler on the wrapper.
      img.setAttribute('role', 'button');
      img.setAttribute('tabindex', '0');
      img.setAttribute(
        'aria-label',
        `${img.alt || 'Report image'} — click to enlarge`,
      );

      if (img.complete) {
        recordIntrinsic(img);
        return;
      }

      remaining += 1;
      img.classList.add('report-image-loading');
      img.setAttribute('aria-busy', 'true');

      const onLoad = () => markDone(img);
      const onError = () => markBroken(img);
      const timeout = window.setTimeout(() => markBroken(img), IMAGE_LOAD_TIMEOUT_MS);

      img.addEventListener('load', onLoad, { once: true });
      img.addEventListener('error', onError, { once: true });

      cleanupFns.push(() => {
        window.clearTimeout(timeout);
        img.removeEventListener('load', onLoad);
        img.removeEventListener('error', onError);
      });
    });

    setIsLoadingImages(remaining > 0);

    return () => {
      isMounted = false;
      cleanupFns.forEach((cleanup) => cleanup());
    };
  }, [html]);

  const openZoom = useCallback((img: HTMLImageElement) => {
    if (img.classList.contains('report-image-fallback')) return;
    const src = img.currentSrc || img.src;
    if (!src) return;
    setZoomed({ src, alt: img.alt });
  }, []);

  const onClick = useCallback(
    (e: React.MouseEvent<HTMLDivElement>) => {
      const target = e.target as HTMLElement;
      const img = target.closest('img') as HTMLImageElement | null;
      if (!img) return;
      e.preventDefault();
      openZoom(img);
    },
    [openZoom],
  );

  const onKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLDivElement>) => {
      if (e.key !== 'Enter' && e.key !== ' ') return;
      const img = (e.target as HTMLElement).closest('img') as
        | HTMLImageElement
        | null;
      if (!img) return;
      e.preventDefault();
      openZoom(img);
    },
    [openZoom],
  );

  return (
    <>
      <div
        aria-busy={isLoadingImages || undefined}
        aria-label={isLoadingImages ? skeletonLabel : undefined}
        ref={ref}
        onClick={onClick}
        onKeyDown={onKeyDown}
        className={`report-rich-html ${isLoadingImages ? 'is-loading' : ''} ${className || ''}`}
        dangerouslySetInnerHTML={{ __html: html }}
      />
      {zoomed ? (
        <Lightbox
          slides={[{ src: zoomed.src, alt: zoomed.alt }]}
          index={0}
          setIndex={(next) => {
            // The library calls setIndex(undefined) on close (Escape or
            // backdrop click); any defined value means "stay open on that
            // slide" — we only have one slide so it's effectively no-op.
            if (next === undefined) setZoomed(null);
          }}
        />
      ) : null}
    </>
  );
}
