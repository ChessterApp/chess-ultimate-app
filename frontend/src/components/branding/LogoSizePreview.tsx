'use client';

// Live "does it survive at small sizes?" strip. Renders the org logo — and its
// optional square "mark" — at the exact pixel sizes used by small render sites
// (navbar 28px, admin sidebar 32px, sidebar/coach 40px) on both light and dark
// swatches, so a detailed circular badge shows its mush before it goes live.
// See .ralphy/logo-mark-brief.md Phase C.

const PREVIEW_SIZES = [24, 32, 40] as const;

interface LogoSizePreviewProps {
  logoUrl?: string | null;
  markUrl?: string | null;
  className?: string;
}

function SwatchRow({ label, src, dark }: { label: string; src: string; dark: boolean }) {
  return (
    <div
      className={`flex items-center gap-3 rounded-lg px-3 py-2 ring-1 ${
        dark ? 'bg-gray-900 ring-gray-700' : 'bg-white ring-gray-200'
      }`}
    >
      <span
        className={`w-10 text-[10px] uppercase tracking-wide ${
          dark ? 'text-gray-400' : 'text-gray-500'
        }`}
      >
        {dark ? 'Dark' : 'Light'}
      </span>
      {PREVIEW_SIZES.map(px => (
        // eslint-disable-next-line @next/next/no-img-element
        <img
          key={px}
          src={src}
          alt={`${label} at ${px}px on ${dark ? 'dark' : 'light'}`}
          width={px}
          height={px}
          style={{ width: px, height: px }}
          className="rounded object-contain"
          data-size={px}
        />
      ))}
    </div>
  );
}

export function LogoSizePreview({ logoUrl, markUrl, className = '' }: LogoSizePreviewProps) {
  const rows: Array<{ label: string; src: string }> = [];
  if (logoUrl) rows.push({ label: 'Logo', src: logoUrl });
  if (markUrl) rows.push({ label: 'Mark', src: markUrl });
  if (rows.length === 0) return null;

  return (
    <div className={`space-y-3 ${className}`} data-testid="logo-size-preview">
      {rows.map(row => (
        <div key={row.label} className="space-y-2">
          <span className="block text-xs font-medium text-gray-700 dark:text-gray-300">
            {row.label} at actual size (24 / 32 / 40px)
          </span>
          <div className="flex flex-wrap gap-3">
            <SwatchRow label={row.label} src={row.src} dark={false} />
            <SwatchRow label={row.label} src={row.src} dark />
          </div>
        </div>
      ))}
      <p className="text-xs text-gray-500 dark:text-gray-400">
        This is how the logo renders in the navbar, sidebar, and coach avatar. If
        it looks like mush here, upload a simpler square “mark”.
      </p>
    </div>
  );
}
