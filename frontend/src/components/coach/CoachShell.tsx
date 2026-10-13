'use client';

import React, { useCallback, useRef, useState } from 'react';
import { useTranslations } from 'next-intl';
import { motion, type PanInfo } from 'framer-motion';
import type { OnScreenKeyboard } from '@/hooks/useOnScreenKeyboard';
import { detentCss, detentHeights, snapDetent, type Detent, type SheetAction } from '@/lib/coach/sheet-detent';

interface CoachShellProps {
  /** The context bar. */
  bar: React.ReactNode;
  /** Over the board (the play strip's coach row); hidden while the sheet is full. */
  above?: React.ReactNode;
  /** The board, fluid: it fills the stage's free square. */
  board: React.ReactNode;
  /** Under the board (move strip, the student's row); hidden while the sheet is full. */
  below?: React.ReactNode;
  /** px that `above` + `below` take, so peek leaves the board the full width. */
  stageChrome: number;
  detent: Detent;
  onSheet: (action: SheetAction) => void;
  /** The coach: the chat in its peek / thread view. */
  sheet: React.ReactNode;
  /** iOS does not resize the page for the keyboard: the shell pins itself to what is left. */
  keyboard: OnScreenKeyboard;
}

/**
 * The coach on phones and portrait tablets (< 1024px): context bar, a
 * full-bleed board, and the coach as a bottom sheet with three detents. All
 * sizing is CSS (dvh, container units, the detents' calc()) — nothing is
 * measured to lay it out, so the first paint is the final one. A drag
 * measures the shell once, at release, to pick the detent.
 */
export default function CoachShell({ bar, above, board, below, stageChrome, detent, onSheet, sheet, keyboard }: CoachShellProps) {
  const t = useTranslations('coach');
  const shellRef = useRef<HTMLDivElement>(null);
  const sheetRef = useRef<HTMLElement>(null);
  const full = detent === 'full';

  // While dragged the sheet follows the finger in px; released it snaps to a detent.
  const [dragHeight, setDragHeight] = useState<number | null>(null);
  const dragStart = useRef(0);
  const dragged = useRef(false);

  const heights = useCallback(() => {
    const shell = shellRef.current;
    const barEl = shell?.firstElementChild as HTMLElement | null;
    return detentHeights({
      height: shell?.clientHeight ?? 0,
      width: shell?.clientWidth ?? 0,
      bar: barEl?.offsetHeight ?? 0,
      stageChrome: full ? 0 : stageChrome,
    });
  }, [full, stageChrome]);

  const onPanStart = () => {
    dragged.current = true;
    dragStart.current = sheetRef.current?.getBoundingClientRect().height ?? 0;
    setDragHeight(dragStart.current);
  };
  const onPan = (_e: PointerEvent, info: PanInfo) => {
    const max = heights().full;
    setDragHeight(Math.max(0, Math.min(max, dragStart.current - info.offset.y)));
  };
  const onPanEnd = (_e: PointerEvent, info: PanInfo) => {
    const released = Math.max(0, dragStart.current - info.offset.y);
    onSheet({ type: 'snap', detent: snapDetent(released, info.velocity.y, heights()) });
    setDragHeight(null);
  };

  const css = detentCss(stageChrome);

  return (
    <div
      ref={shellRef}
      className="coach-shell fixed inset-x-0 top-0 z-40 flex h-[100dvh] flex-col overflow-hidden bg-(--coach-bg) [container-type:size]"
      style={keyboard.open ? { top: keyboard.top, height: keyboard.height } : undefined}
      data-testid="coach-shell"
      data-detent={detent}
    >
      {bar}

      <div className="relative flex min-h-0 flex-1 flex-col">
        {!full && above}
        <div className="relative min-h-0 flex-1">
          {board}
          {full && (
            // The pinned mini-board: one tap brings the board back.
            <button
              type="button"
              onClick={() => onSheet({ type: 'mini_board_tap' })}
              aria-label={t('showBoard')}
              data-testid="mini-board"
              className="absolute inset-0 z-10 focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--coach-accent)"
            />
          )}
        </div>
        {!full && below}
      </div>

      <section
        ref={sheetRef}
        aria-label={t('coachLabel')}
        className={`relative z-10 flex shrink-0 flex-col overflow-hidden rounded-t-[22px] border-t border-(--coach-border) bg-(--coach-surface) pb-[env(safe-area-inset-bottom)] shadow-(--coach-shadow) ${
          dragHeight === null ? 'coach-sheet-glide' : ''
        }`}
        style={{ height: dragHeight === null ? css[detent] : dragHeight }}
        data-testid="coach-sheet"
      >
        <motion.button
          type="button"
          onPanStart={onPanStart}
          onPan={onPan}
          onPanEnd={onPanEnd}
          onPointerDown={() => {
            dragged.current = false;
          }}
          onClick={() => {
            // The click that ends a drag is not a tap.
            if (!dragged.current) onSheet({ type: 'toggle' });
          }}
          onKeyDown={(e) => {
            if (e.key === 'ArrowUp') {
              e.preventDefault();
              onSheet({ type: 'expand' });
            } else if (e.key === 'ArrowDown') {
              e.preventDefault();
              onSheet({ type: 'collapse' });
            }
          }}
          aria-label={detent === 'peek' ? t('sheetExpand') : t('sheetCollapse')}
          aria-expanded={detent !== 'peek'}
          data-testid="sheet-grabber"
          className="flex h-11 w-full shrink-0 touch-none cursor-grab items-center justify-center focus-visible:outline focus-visible:outline-2 focus-visible:-outline-offset-2 focus-visible:outline-(--coach-accent) active:cursor-grabbing"
        >
          <span className="h-[5px] w-[38px] rounded-full bg-(--coach-grabber)" aria-hidden />
        </motion.button>
        <div className="min-h-0 flex-1">{sheet}</div>
      </section>
    </div>
  );
}
