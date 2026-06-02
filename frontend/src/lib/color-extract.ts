// PRD §11.2 #3 — Logo color extraction (Phase 1 carryover #3).
//
// Pure pixel-based extraction so we don't need node-vibrant's heavy
// canvas-bound runtime in vitest. Caller decodes the image to an
// ImageData and hands it here.

export interface ExtractedPalette {
  /** Hex (#rrggbb) — dominant color, used as Primary. */
  dominant: string;
  /** Highest-saturation cluster — used as Accent. */
  accent: string;
  /** Low-saturation cluster — used as Secondary (text/background). */
  muted: string;
}

interface RGB {
  r: number;
  g: number;
  b: number;
}

function toHex(c: RGB): string {
  const h = (n: number) => Math.max(0, Math.min(255, Math.round(n))).toString(16).padStart(2, '0');
  return `#${h(c.r)}${h(c.g)}${h(c.b)}`;
}

function rgbToHsl({ r, g, b }: RGB): { h: number; s: number; l: number } {
  const rr = r / 255;
  const gg = g / 255;
  const bb = b / 255;
  const max = Math.max(rr, gg, bb);
  const min = Math.min(rr, gg, bb);
  const l = (max + min) / 2;
  let h = 0;
  let s = 0;
  if (max !== min) {
    const d = max - min;
    s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
    if (max === rr) h = ((gg - bb) / d + (gg < bb ? 6 : 0));
    else if (max === gg) h = ((bb - rr) / d + 2);
    else h = ((rr - gg) / d + 4);
    h *= 60;
  }
  return { h, s, l };
}

/**
 * Quantise a 32-bit RGBA pixel buffer into a small palette by 5-bit
 * bucketing (32^3 = 32k buckets, max). Returns buckets sorted by count.
 */
function bucketise(pixels: Uint8Array | Uint8ClampedArray): { color: RGB; count: number }[] {
  const buckets = new Map<number, { color: RGB; count: number }>();
  for (let i = 0; i < pixels.length; i += 4) {
    const a = pixels[i + 3];
    if (a < 200) continue; // skip near-transparent
    const r = pixels[i];
    const g = pixels[i + 1];
    const b = pixels[i + 2];
    // Skip near-white and near-black "frame" pixels.
    if (r > 245 && g > 245 && b > 245) continue;
    if (r < 10 && g < 10 && b < 10) continue;
    // 5-bit per channel quantisation.
    const key = ((r >> 3) << 10) | ((g >> 3) << 5) | (b >> 3);
    const bucket = buckets.get(key);
    if (bucket) {
      bucket.color.r = (bucket.color.r * bucket.count + r) / (bucket.count + 1);
      bucket.color.g = (bucket.color.g * bucket.count + g) / (bucket.count + 1);
      bucket.color.b = (bucket.color.b * bucket.count + b) / (bucket.count + 1);
      bucket.count++;
    } else {
      buckets.set(key, { color: { r, g, b }, count: 1 });
    }
  }
  return [...buckets.values()].sort((a, b) => b.count - a.count);
}

export function extractPalette(
  pixels: Uint8Array | Uint8ClampedArray,
): ExtractedPalette {
  const buckets = bucketise(pixels);
  if (buckets.length === 0) {
    return { dominant: '#1a73e8', accent: '#ffd700', muted: '#ffffff' };
  }
  // Dominant: most frequent bucket.
  const dominant = buckets[0].color;
  // Accent: pick the bucket with the highest saturation × log(count).
  // This avoids returning the same dominant color when the logo is largely
  // monochrome — fall back to dominant if no saturated bucket exists.
  let bestAccent = buckets[0];
  let bestAccentScore = 0;
  for (const b of buckets.slice(0, 32)) {
    const hsl = rgbToHsl(b.color);
    const score = hsl.s * Math.log(1 + b.count);
    if (score > bestAccentScore) {
      bestAccentScore = score;
      bestAccent = b;
    }
  }
  // Muted: lowest-saturation cluster that's still bright (light) — useful as
  // secondary color (text/background). Default to white when nothing
  // matches.
  let muted: RGB = { r: 255, g: 255, b: 255 };
  let bestLight = 0;
  for (const b of buckets.slice(0, 32)) {
    const hsl = rgbToHsl(b.color);
    if (hsl.s < 0.25 && hsl.l > bestLight) {
      bestLight = hsl.l;
      muted = b.color;
    }
  }
  return {
    dominant: toHex(dominant),
    accent: toHex(bestAccent.color),
    muted: toHex(muted),
  };
}

/**
 * Browser convenience helper — decodes an image url or data-url through a
 * 64×64 off-screen canvas, then extracts a palette. Returns null when the
 * environment can't decode (SSR, OffscreenCanvas not available).
 */
export async function extractPaletteFromUrl(
  url: string,
): Promise<ExtractedPalette | null> {
  if (typeof document === 'undefined') return null;
  return new Promise(resolve => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onerror = () => resolve(null);
    img.onload = () => {
      try {
        const size = 64;
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        if (!ctx) return resolve(null);
        ctx.drawImage(img, 0, 0, size, size);
        const data = ctx.getImageData(0, 0, size, size).data;
        resolve(extractPalette(data));
      } catch {
        resolve(null);
      }
    };
    img.src = url;
  });
}
