'use client';

import { useEffect, useRef, useState } from 'react';

interface AvailabilityResult {
  available: boolean;
  reason?: string;
  message?: string;
  suggestions?: string[];
}

interface Props {
  value: string;
  onChange: (next: string) => void;
  onAvailabilityChange?: (ok: boolean) => void;
}

// PRD §6.5 — debounced 300ms availability check.
export function SlugAvailabilityInput({ value, onChange, onAvailabilityChange }: Props) {
  const [state, setState] = useState<
    'idle' | 'checking' | 'ok' | 'bad'
  >('idle');
  const [info, setInfo] = useState<AvailabilityResult | null>(null);
  const abortRef = useRef<AbortController | null>(null);
  const timerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => {
    if (!value || value.length < 2) {
      setState('idle');
      setInfo(null);
      onAvailabilityChange?.(false);
      return;
    }

    if (timerRef.current) clearTimeout(timerRef.current);
    setState('checking');

    timerRef.current = setTimeout(async () => {
      if (abortRef.current) abortRef.current.abort();
      abortRef.current = new AbortController();
      try {
        const res = await fetch(
          `/api/subdomains/check?slug=${encodeURIComponent(value)}`,
          { signal: abortRef.current.signal },
        );
        const body = (await res.json()) as AvailabilityResult;
        setInfo(body);
        setState(body.available ? 'ok' : 'bad');
        onAvailabilityChange?.(!!body.available);
      } catch (err) {
        if ((err as Error).name === 'AbortError') return;
        setState('idle');
      }
    }, 300);

    return () => {
      if (timerRef.current) clearTimeout(timerRef.current);
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const reasonText = (() => {
    if (!info) return null;
    if (info.available) return 'Available';
    if (info.message) return info.message;
    if (info.reason === 'taken') return 'Taken — try one below';
    if (info.reason === 'reserved') return 'Reserved name — try one below';
    if (info.reason === 'invalid_format')
      return 'Use lowercase letters, numbers, and hyphens (2-30 chars).';
    return 'Unavailable';
  })();

  const dotColor =
    state === 'ok'
      ? 'bg-green-500'
      : state === 'bad'
      ? 'bg-red-500'
      : state === 'checking'
      ? 'bg-yellow-400'
      : 'bg-gray-300';

  return (
    <div>
      <div className="flex items-stretch rounded-lg border border-gray-300 overflow-hidden focus-within:border-blue-500 focus-within:ring-2 focus-within:ring-blue-100">
        <input
          type="text"
          value={value}
          onChange={e => onChange(e.target.value.toLowerCase())}
          placeholder="almatychess"
          aria-label="Subdomain slug"
          className="flex-1 min-w-0 px-3 py-2 text-sm outline-none"
        />
        <span className="shrink-0 whitespace-nowrap bg-gray-50 border-l border-gray-200 px-3 py-2 text-sm text-gray-600 inline-flex items-center">
          .chesster.io
        </span>
      </div>

      <div className="mt-2 flex items-center gap-2 text-xs">
        <span
          aria-hidden
          className={`inline-block h-2 w-2 rounded-full ${dotColor}`}
        />
        <span
          className={
            state === 'ok'
              ? 'text-green-700'
              : state === 'bad'
              ? 'text-red-700'
              : 'text-gray-500'
          }
        >
          {state === 'checking' ? 'Checking…' : reasonText ?? 'Enter a name'}
        </span>
      </div>

      {info?.suggestions && info.suggestions.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {info.suggestions.map(s => (
            <button
              key={s}
              type="button"
              onClick={() => onChange(s)}
              className="text-xs px-2 py-1 rounded border border-gray-300 hover:bg-gray-50"
            >
              {s}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
