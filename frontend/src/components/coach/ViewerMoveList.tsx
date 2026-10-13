'use client';

import React, { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';

interface ViewerMoveListProps {
  moves: string[];
  /** -1 = the start position. */
  currentIndex: number;
  onJump: (index: number) => void;
  layout?: 'strip' | 'list';
  maxHeight?: number;
}

/** The opened game's moves; tap one to jump there. A one-line strip on phones, numbered rows beside the board on desktop. */
export default function ViewerMoveList({ moves, currentIndex, onJump, layout = 'strip', maxHeight }: ViewerMoveListProps) {
  const t = useTranslations('coach');
  const activeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [currentIndex]);

  const move = (i: number) => (
    <button
      key={i}
      ref={i === currentIndex ? activeRef : undefined}
      type="button"
      onClick={() => onJump(i)}
      aria-current={i === currentIndex}
      className={`min-h-11 shrink-0 rounded-md px-2 text-sm tabular-nums transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent) ${
        i === currentIndex ? 'bg-(--coach-accent) font-semibold text-white' : 'text-(--coach-text) hover:bg-white/10'
      } ${layout === 'list' ? 'min-h-9 text-left' : ''}`}
    >
      {moves[i]}
    </button>
  );

  if (layout === 'list') {
    const rows = Array.from({ length: Math.ceil(moves.length / 2) }, (_, r) => r);
    return (
      <nav
        aria-label={t('viewerMoves')}
        className="overflow-y-auto rounded-xl border border-(--coach-border) bg-(--coach-surface) p-1"
        style={{ maxHeight }}
        data-testid="viewer-moves"
      >
        <ol className="grid grid-cols-[2.25rem_1fr_1fr] gap-x-1">
          {rows.map((r) => (
            <li key={r} className="contents">
              <span className="flex items-center justify-end pr-1 text-xs tabular-nums text-(--coach-muted)">{r + 1}.</span>
              {move(2 * r)}
              {2 * r + 1 < moves.length ? move(2 * r + 1) : <span />}
            </li>
          ))}
        </ol>
      </nav>
    );
  }

  return (
    <nav
      aria-label={t('viewerMoves')}
      className="flex items-center gap-0.5 overflow-x-auto rounded-xl border border-(--coach-border) bg-(--coach-surface) px-1 [scrollbar-width:none]"
      data-testid="viewer-moves"
    >
      {moves.map((_, i) => (
        <React.Fragment key={i}>
          {i % 2 === 0 && <span className="shrink-0 pl-1 text-xs tabular-nums text-(--coach-muted)">{i / 2 + 1}.</span>}
          {move(i)}
        </React.Fragment>
      ))}
    </nav>
  );
}
