'use client';

import React, { useEffect } from 'react';
import { useTranslations } from 'next-intl';
import { squareToPercent } from '@/lib/coach/board-geometry';
import { VERDICT_SYMBOL, type MoveVerdict, type VerdictKind } from '@/lib/coach/play';

const TONE: Record<VerdictKind, string> = {
  blunder: 'bg-(--coach-danger) text-white',
  mistake: 'bg-(--coach-warning) text-black',
  inaccuracy: 'bg-(--coach-info) text-black',
  good: 'bg-(--coach-success) text-white',
  brilliant: 'bg-(--coach-accent) text-white',
  best: 'bg-(--coach-success) text-white',
};

const LABEL_KEY: Record<VerdictKind, string> = {
  blunder: 'verdictBlunder',
  mistake: 'verdictMistake',
  inaccuracy: 'verdictInaccuracy',
  good: 'verdictGood',
  brilliant: 'verdictBrilliant',
  best: 'verdictBest',
};

/** The verdict's words, e.g. "h4: blunder, better was e4". */
export function useVerdictLine() {
  const t = useTranslations('coach');
  return (v: MoveVerdict) => {
    const better = v.kind !== 'best' && v.best && v.best !== v.san ? `, ${t('gameBetterWas', { move: v.best })}` : '';
    return `${v.san}: ${t(LABEL_KEY[v.kind])}${better}`;
  };
}

/**
 * A coloured badge on the move's destination square. Lay it over the board
 * (the parent is `position: relative` and exactly the board's size).
 */
export function VerdictBadge({ verdict, orientation }: { verdict: MoveVerdict; orientation: 'white' | 'black' }) {
  const line = useVerdictLine();
  const pos = squareToPercent(verdict.square, orientation);
  if (!pos) return null;
  return (
    <span
      key={`${verdict.square}-${verdict.kind}`}
      role="img"
      aria-label={line(verdict)}
      data-testid="verdict-badge"
      data-kind={verdict.kind}
      className={`coach-badge-pop pointer-events-none absolute z-10 flex h-[22px] min-w-[22px] items-center justify-center rounded-full px-1 text-[11px] font-bold leading-none shadow-md ring-2 ring-(--coach-bg) ${TONE[verdict.kind]}`}
      // Top-right corner of the square, half outside it (as on Lichess / Chess.com).
      style={{ left: `calc(${pos.left + 12.5}% - 14px)`, top: `calc(${pos.top}% - 8px)` }}
    >
      {VERDICT_SYMBOL[verdict.kind]}
    </span>
  );
}

/** One-line toast with the verdict; fades out on its own. */
export function VerdictToast({ verdict, onDone, ms = 3500 }: { verdict: MoveVerdict; onDone: () => void; ms?: number }) {
  const line = useVerdictLine();
  useEffect(() => {
    const timer = setTimeout(onDone, ms);
    return () => clearTimeout(timer);
  }, [verdict, onDone, ms]);
  return (
    <div
      role="status"
      data-testid="verdict-toast"
      className="animate-fade-in pointer-events-none absolute inset-x-2 bottom-2 z-20 flex justify-center"
    >
      <span className="flex max-w-full items-center gap-2 truncate rounded-full border border-(--coach-border) bg-(--coach-surface)/95 px-3 py-1.5 text-sm text-(--coach-text) shadow-lg backdrop-blur">
        <span className={`inline-flex h-5 min-w-5 shrink-0 items-center justify-center rounded-full px-1 text-[10px] font-bold ${TONE[verdict.kind]}`}>
          {VERDICT_SYMBOL[verdict.kind]}
        </span>
        <span className="truncate">{line(verdict)}</span>
      </span>
    </div>
  );
}
