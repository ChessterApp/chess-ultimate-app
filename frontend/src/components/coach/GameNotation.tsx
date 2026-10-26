'use client';

import React, { useEffect, useRef } from 'react';
import { useTranslations } from 'next-intl';

export interface GameVariation {
  at_ply: number;
  moves: string[];
}

interface GameNotationProps {
  /** The main line, SAN from the start. */
  moves: string[];
  /** Lines taken back, each anchored at the ply of the main line it left (the game view's `variations`). */
  variations?: GameVariation[];
  /** The main-line move shown on the board (its index); -1 = the start. Null while a side line is shown. */
  currentIndex: number | null;
  /** The side line shown, if any: its index in `variations` and how many of its moves are on the board. */
  currentVariation?: { index: number; count: number } | null;
  onJump: (index: number) => void;
  onJumpVariation: (index: number, count: number) => void;
}

/** «1.e4 e5 2.Nf3 ( 2.Qh5 d6 3.Bc4 g6 ) Nc6 …» — the game's notation with every line it went through, the way the
 *  games database shows a main line with its alternatives (Alexander, 26.10). Main-line moves jump the board
 *  to that ply; a move of a side line shows that line on the board (the game itself goes on). */
export default function GameNotation({ moves, variations = [], currentIndex, currentVariation, onJump, onJumpVariation }: GameNotationProps) {
  const t = useTranslations('coach');
  const activeRef = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    activeRef.current?.scrollIntoView?.({ block: 'nearest', inline: 'nearest' });
  }, [currentIndex, currentVariation, moves.length]);

  const byPly = new Map<number, Array<{ index: number; v: GameVariation }>>();
  variations.forEach((v, index) => {
    const list = byPly.get(v.at_ply) ?? [];
    list.push({ index, v });
    byPly.set(v.at_ply, list);
  });

  const moveButton = (san: string, active: boolean, onClick: () => void, key: string) => (
    <button
      key={key}
      ref={active ? activeRef : undefined}
      type="button"
      onClick={onClick}
      aria-current={active}
      className={`h-6 shrink-0 rounded-[6px] px-[5px] text-[13px] tabular-nums transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent) ${
        active ? 'bg-(--coach-surface-2) font-semibold text-(--coach-text)' : 'text-(--coach-muted) hover:text-(--coach-text)'
      }`}
    >
      {san}
    </button>
  );

  const sideLine = (index: number, v: GameVariation) => (
    <span key={`v${index}`} className="inline-flex flex-wrap items-center gap-0.5 rounded-md bg-(--coach-surface-1,rgba(255,255,255,0.04)) px-1 text-(--coach-muted)" data-testid="game-variation">
      <span className="text-[12px]">(</span>
      {v.moves.map((san, k) => {
        const ply = v.at_ply + k + 1;
        const number = ply % 2 === 1 ? `${(ply + 1) / 2}.` : k === 0 ? `${ply / 2}…` : '';
        const active = !!currentVariation && currentVariation.index === index && currentVariation.count === k + 1;
        return (
          <React.Fragment key={k}>
            {number && <span className="text-[12px] tabular-nums text-(--coach-muted)/70">{number}</span>}
            {moveButton(san, active, () => onJumpVariation(index, k + 1), `v${index}-${k}`)}
          </React.Fragment>
        );
      })}
      <span className="text-[12px]">)</span>
    </span>
  );

  return (
    <div className="flex min-h-full flex-col border-b border-(--coach-border) bg-(--coach-bg)" data-testid="game-notation">
      <nav aria-label={t('viewerMoves')} className="flex min-h-0 flex-1 flex-wrap content-start items-center gap-0.5 overflow-y-auto px-2 py-1 [scrollbar-width:thin]">
        {moves.length === 0 && variations.length === 0 && <span className="px-1 text-sm text-(--coach-muted)">{t('moveStripEmpty')}</span>}
        {byPly.get(0)?.map(({ index, v }) => sideLine(index, v))}
        {moves.map((san, i) => (
          <React.Fragment key={i}>
            {i % 2 === 0 && <span className="shrink-0 pl-1 text-[12px] tabular-nums text-(--coach-muted)/70">{i / 2 + 1}.</span>}
            {i % 2 === 1 && byPly.has(i) && <span className="shrink-0 pl-1 text-[12px] tabular-nums text-(--coach-muted)/70">{(i + 1) / 2}…</span>}
            {moveButton(san, currentIndex === i, () => onJump(i), `m${i}`)}
            {byPly.get(i + 1)?.map(({ index, v }) => sideLine(index, v))}
          </React.Fragment>
        ))}
      </nav>
    </div>
  );
}
