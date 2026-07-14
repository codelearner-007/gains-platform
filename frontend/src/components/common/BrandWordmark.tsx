import Image from 'next/image';

// Intrinsic logo dimensions (public/gains-logo.png): 1200 x 279.
const LOGO_RATIO = 1200 / 279;

interface BrandWordmarkProps {
  /** Rendered height in px; width is derived from the logo aspect ratio. */
  height?: number;
  className?: string;
  /** Set on the above-the-fold logo (nav/hero) to skip lazy-loading. */
  priority?: boolean;
}

/**
 * The GAINS wordmark. Renders the brand logo from public/; `alt="GAINS"` is the
 * text fallback shown if the image is ever missing or blocked by a client.
 * Single source of truth for the mark across home, auth, and legal chrome.
 */
export function BrandWordmark({ height = 28, className, priority = false }: BrandWordmarkProps) {
  const width = Math.round(height * LOGO_RATIO);
  return (
    <Image
      src="/gains-logo.png"
      alt="GAINS"
      width={width}
      height={height}
      priority={priority}
      className={className}
      // Pin the display box to the intended px (matching the intrinsic ratio) so
      // Tailwind's `img { height: auto }` preflight and next/image's served
      // resolution cannot resize the mark. Callers pass layout classes only.
      style={{ width, height }}
    />
  );
}
