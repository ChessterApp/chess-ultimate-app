'use client';

import { loomEmbedUrl } from '@/lib/loom';

interface Props {
  /** Loom share URL, embed URL, or bare video id. */
  url: string | null | undefined;
  /** Optional caption shown above the iframe. */
  title?: string;
  /** Aspect ratio for the embed (default 16:9). */
  aspectRatio?: '16/9' | '4/3' | '1/1';
}

/**
 * Loom video embed (PRD §11.3 #5).
 *
 * Renders nothing when the URL doesn't resolve to a valid Loom embed.
 * Aspect-ratio CSS keeps the iframe responsive without external CSS.
 */
export function LoomEmbed({ url, title, aspectRatio = '16/9' }: Props) {
  const embedUrl = loomEmbedUrl(url);
  if (!embedUrl) return null;

  return (
    <div className="rounded-lg overflow-hidden border border-gray-200 bg-black">
      {title && (
        <div className="px-3 py-2 text-sm font-medium text-gray-700 bg-gray-50">
          {title}
        </div>
      )}
      <div
        className="relative w-full"
        style={{ aspectRatio: aspectRatio.replace('/', ' / ') }}
      >
        <iframe
          src={embedUrl}
          title={title || 'Loom video'}
          allowFullScreen
          className="absolute inset-0 h-full w-full"
        />
      </div>
    </div>
  );
}
