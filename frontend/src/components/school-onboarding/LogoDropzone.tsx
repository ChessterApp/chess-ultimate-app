'use client';

import { useCallback, useRef, useState } from 'react';
import { extractPaletteFromUrl } from '@/lib/color-extract';
import { ANALYTICS_EVENTS, track } from '@/lib/analytics/events';

// PRD §11.2 #3 + Phase 1 carryover #1 — drag-drop logo input with built-in
// square cropper. We deliberately avoid `react-easy-crop` here: a 200-line
// component is cheaper than a 50KB dep, and the wizard only needs centred
// square cropping.

const MAX_BYTES = 5 * 1024 * 1024; // 5 MB

export interface LogoDropzoneProps {
  value?: string;
  onChange: (dataUrl: string) => void;
  onPaletteExtracted?: (palette: { primary: string; secondary: string; accent: string }) => void;
}

export function LogoDropzone({ value, onChange, onPaletteExtracted }: LogoDropzoneProps) {
  const [sourceUrl, setSourceUrl] = useState<string | null>(value ?? null);
  const [error, setError] = useState<string | null>(null);
  const [cropZoom, setCropZoom] = useState(1);
  const [dragging, setDragging] = useState(false);
  const fileRef = useRef<HTMLInputElement>(null);

  const ingestFile = useCallback(async (file: File) => {
    setError(null);
    if (!file.type.startsWith('image/')) {
      setError('Only image files are accepted.');
      return;
    }
    if (file.size > MAX_BYTES) {
      setError('File too large (max 5MB).');
      return;
    }
    const url = await readFileAsDataUrl(file);
    setSourceUrl(url);
    setCropZoom(1);
    track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_LOGO_UPLOADED, { size: file.size });
  }, []);

  const finalize = useCallback(async () => {
    if (!sourceUrl) return;
    const cropped = await cropSquareDataUrl(sourceUrl, cropZoom);
    onChange(cropped);
    if (onPaletteExtracted) {
      const palette = await extractPaletteFromUrl(cropped);
      if (palette) {
        onPaletteExtracted({
          primary: palette.dominant,
          secondary: palette.muted,
          accent: palette.accent,
        });
        track(ANALYTICS_EVENTS.SCHOOL_ONBOARDING_COLORS_AUTODETECTED);
      }
    }
  }, [sourceUrl, cropZoom, onChange, onPaletteExtracted]);

  const onDrop = useCallback(
    (e: React.DragEvent) => {
      e.preventDefault();
      setDragging(false);
      const file = e.dataTransfer.files?.[0];
      if (file) void ingestFile(file);
    },
    [ingestFile],
  );

  return (
    <div className="space-y-2">
      <div
        onDragOver={e => {
          e.preventDefault();
          setDragging(true);
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={`rounded-lg border-2 border-dashed p-4 text-center transition-colors ${
          dragging ? 'border-blue-500 bg-blue-50' : 'border-gray-300 bg-gray-50'
        }`}
      >
        {sourceUrl ? (
          <div className="flex flex-col items-center gap-3">
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img
              src={sourceUrl}
              alt="Logo preview"
              style={{
                width: 96,
                height: 96,
                objectFit: 'cover',
                transform: `scale(${cropZoom})`,
              }}
              className="rounded bg-white border"
            />
            <div className="flex flex-wrap items-center justify-center gap-2 text-xs">
              <label className="flex items-center gap-1">
                Zoom
                <input
                  type="range"
                  min={1}
                  max={2}
                  step={0.05}
                  value={cropZoom}
                  onChange={e => setCropZoom(Number(e.target.value))}
                />
              </label>
              <button
                type="button"
                onClick={() => fileRef.current?.click()}
                className="rounded border border-gray-300 px-2 py-1 hover:bg-gray-100"
              >
                Replace
              </button>
              <button
                type="button"
                onClick={() => void finalize()}
                className="rounded bg-blue-600 px-3 py-1 font-medium text-white"
              >
                Use logo
              </button>
            </div>
          </div>
        ) : (
          <>
            <p className="text-sm text-gray-600">Drag and drop a logo here</p>
            <button
              type="button"
              onClick={() => fileRef.current?.click()}
              className="mt-2 rounded border border-gray-300 bg-white px-3 py-1 text-xs"
            >
              or pick a file
            </button>
          </>
        )}
        <input
          ref={fileRef}
          type="file"
          accept="image/*"
          className="hidden"
          onChange={e => {
            const f = e.target.files?.[0];
            if (f) void ingestFile(f);
          }}
        />
      </div>
      {error && <p className="text-xs text-red-600">{error}</p>}
    </div>
  );
}

function readFileAsDataUrl(file: File): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(reader.result as string);
    reader.onerror = () => reject(reader.error);
    reader.readAsDataURL(file);
  });
}

export async function cropSquareDataUrl(
  src: string,
  zoom: number,
  size = 256,
): Promise<string> {
  if (typeof document === 'undefined') return src;
  return new Promise(resolve => {
    const img = new Image();
    img.crossOrigin = 'anonymous';
    img.onerror = () => resolve(src);
    img.onload = () => {
      try {
        const canvas = document.createElement('canvas');
        canvas.width = size;
        canvas.height = size;
        const ctx = canvas.getContext('2d');
        if (!ctx) return resolve(src);
        const min = Math.min(img.width, img.height);
        const cropSize = min / Math.max(1, zoom);
        const sx = (img.width - cropSize) / 2;
        const sy = (img.height - cropSize) / 2;
        ctx.drawImage(img, sx, sy, cropSize, cropSize, 0, 0, size, size);
        resolve(canvas.toDataURL('image/png'));
      } catch {
        resolve(src);
      }
    };
    img.src = src;
  });
}
