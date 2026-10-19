/**
 * BotBoard — a small, view-only chessground board that shows the Chesster
 * bot's puzzle and animates its moves (driven by useTugBot's view). Sized like
 * TugBoard: an integer multiple of 8 off the container width so pieces land on
 * square centres.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { Chessground } from 'chessground';
import type { Api } from 'chessground/api';
import type { Key } from 'chessground/types';
import { orientationFromFen } from '@/lib/tug-of-war/orientation';

import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import '@/styles/chessground-theme.css';

interface BotBoardProps {
  fen: string;
  lastMove?: [string, string];
  /** The puzzle's starting FEN — fixes the orientation to the solver's side. */
  puzzleFen: string;
}

export default function BotBoard({ fen, lastMove, puzzleFen }: BotBoardProps) {
  const measureRef = useRef<HTMLDivElement>(null);
  const elRef = useRef<HTMLDivElement>(null);
  const groundRef = useRef<Api | null>(null);
  const [size, setSize] = useState(0);
  const orientation = orientationFromFen(puzzleFen);

  useEffect(() => {
    if (!elRef.current) return;
    groundRef.current = Chessground(elRef.current, {
      viewOnly: true,
      coordinates: false,
      animation: { enabled: true, duration: 250 },
      highlight: { lastMove: true, check: true },
    });
    return () => {
      groundRef.current?.destroy();
      groundRef.current = null;
    };
  }, []);

  useEffect(() => {
    groundRef.current?.set({
      fen,
      orientation,
      lastMove: lastMove as Key[] | undefined,
    });
  }, [fen, lastMove, orientation]);

  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return;
    const el = measureRef.current;
    if (!el) return;
    const measure = () => {
      const w = el.clientWidth;
      if (w > 0) setSize(Math.floor(w / 8) * 8);
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, []);

  useEffect(() => {
    if (size > 0) groundRef.current?.redrawAll();
  }, [size]);

  return (
    <div ref={measureRef} className="flex w-full justify-center" data-testid="tug-bot-board">
      <div className="overflow-hidden rounded-lg ring-2 ring-red-500/80" style={{ lineHeight: 0 }}>
        <div
          ref={elRef}
          className="chessground-board"
          style={{ width: size || undefined, height: size || undefined }}
        />
      </div>
    </div>
  );
}
