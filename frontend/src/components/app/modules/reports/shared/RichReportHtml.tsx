'use client';

import { useEffect, useRef, useState } from 'react';

interface RichReportHtmlProps {
  html: string;
  className?: string;
  skeletonLabel?: string;
}

const IMAGE_LOAD_TIMEOUT_MS = 12000;

/**
 * Renders sanitized report HTML that may contain Schoology images/LaTeX SVGs.
 * Adds per-image shimmer skeletons while injected <img> elements load and
 * replaces broken images with a readable fallback instead of a browser glyph.
 * The HTML must be sanitized before being passed in.
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

  useEffect(() => {
    const root = ref.current;
    if (!root) return;

    const imgs = Array.from(root.querySelectorAll('img'));
    let remaining = 0;
    let isMounted = true;
    const cleanupFns: Array<() => void> = [];

    const markDone = (img: HTMLImageElement) => {
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
      if (img.complete) return;

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

  return (
    <div
      aria-busy={isLoadingImages || undefined}
      aria-label={isLoadingImages ? skeletonLabel : undefined}
      ref={ref}
      className={`report-rich-html ${isLoadingImages ? 'is-loading' : ''} ${className || ''}`}
      dangerouslySetInnerHTML={{ __html: html }}
    />
  );
}
