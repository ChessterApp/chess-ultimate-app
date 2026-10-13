'use client';

import React, { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';
import { ChevronLeft, ChevronRight } from 'lucide-react';

interface MoveStripProps {
  moves: string[];
  /** The move shown on the board; -1 = the start position. */
  currentIndex: number;
  onJump: (index: number) => void;
  onPrev: () => void;
  onNext: () => void;
}

const navButton =
  'flex h-9 w-11 shrink-0 items-center justify-center text-(--coach-text) transition-colors hover:bg-white/5 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--coach-accent) disabled:opacity-30';

/**
 * The 36px strip under the full-bleed board on phones: the game's moves in one
 * sideways-scrolling line (tap to jump, the current one highlighted) and ‹ ›.
 */
export default function MoveStrip({ moves, currentIndex, onJump, onPrev, onNext }: MoveStripProps) {
  const t = useTranslations('coach');
  const activeRef = useRef<HTMLButtonElement>(null);

  useEffect(() => {
    activeRef.current?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [currentIndex, moves.length]);

  return (
    <div className="flex h-9 shrink-0 items-center border-b border-(--coach-border) bg-(--coach-bg)" data-testid="move-strip">
      <nav aria-label={t('viewerMoves')} className="flex h-full min-w-0 flex-1 items-center gap-0.5 overflow-x-auto px-2 [scrollbar-width:none]">
        {moves.length === 0 && <span className="px-1 text-sm text-(--coach-muted)">{t('moveStripEmpty')}</span>}
        {moves.map((san, i) => (
          <React.Fragment key={i}>
            {i % 2 === 0 && <span className="shrink-0 pl-1 text-[13px] tabular-nums text-(--coach-muted)/70">{i / 2 + 1}.</span>}
            <button
              ref={i === currentIndex ? activeRef : undefined}
              type="button"
              onClick={() => onJump(i)}
              aria-current={i === currentIndex}
              className={`h-7 shrink-0 rounded-[7px] px-[7px] text-sm tabular-nums transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent) ${
                i === currentIndex ? 'bg-(--coach-surface-2) font-semibold text-(--coach-text)' : 'text-(--coach-muted) hover:text-(--coach-text)'
              }`}
            >
              {san}
            </button>
          </React.Fragment>
        ))}
      </nav>
      <button type="button" onClick={onPrev} disabled={currentIndex < 0} aria-label={t('previousMove')} className={navButton}>
        <ChevronLeft size={18} aria-hidden />
      </button>
      <button
        type="button"
        onClick={onNext}
        disabled={currentIndex >= moves.length - 1}
        aria-label={t('nextMove')}
        className={navButton}
      >
        <ChevronRight size={18} aria-hidden />
      </button>
    </div>
  );
}
