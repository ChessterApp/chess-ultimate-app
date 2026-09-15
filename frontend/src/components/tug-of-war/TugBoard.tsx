/**
 * TugBoard — a thin, self-contained chess board for Tug of War.
 *
 * Built on chessground (already a dependency) + chess.js. It shows one puzzle,
 * lets the solving team play the solution line (tap-piece → tap-square, drag
 * optional), auto-plays the scripted opponent replies, and reports only two
 * outcomes upward: `onSolved` (whole line played) and `onWrong` (a legal move
 * that isn't the solution). Illegal moves are impossible — only legal
 * destinations are offered.
 */

'use client';

import { useEffect, useRef, useState } from 'react';
import { Chess, SQUARES } from 'chess.js';
import type { Square } from 'chess.js';
import { Chessground } from 'chessground';
import type { Api } from 'chessground/api';
import type { Key } from 'chessground/types';
import type { TugPuzzle } from '@/lib/tug-of-war/types';
import { evaluateTeamMove } from '@/lib/tug-of-war/validateMove';
import { orientationFromFen } from '@/lib/tug-of-war/orientation';

import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import 'chessground/assets/chessground.cburnett.css';

/** Delay before the opponent's scripted reply auto-plays (ms). */
const OPPONENT_REPLY_DELAY = 300;

interface TugBoardProps {
  puzzle: TugPuzzle;
  /** Team accent — drives the board frame color only. */
  accent: 'blue' | 'orange';
  onSolved: () => void;
  onWrong: () => void;
  /** When true the board is frozen (match over). */
  disabled?: boolean;
}

function computeDests(chess: Chess): Map<Key, Key[]> {
  const dests = new Map<Key, Key[]>();
  for (const sq of SQUARES) {
    const moves = chess.moves({ square: sq, verbose: true });
    if (moves.length) dests.set(sq, moves.map((m) => m.to as Key));
  }
  return dests;
}

const FRAME: Record<'blue' | 'orange', string> = {
  blue: 'ring-4 ring-blue-500 shadow-[0_0_0_2px_rgba(59,130,246,0.35)]',
  orange: 'ring-4 ring-red-500 shadow-[0_0_0_2px_rgba(239,68,68,0.35)]',
};

export default function TugBoard({ puzzle, accent, onSolved, onWrong, disabled }: TugBoardProps) {
  const elRef = useRef<HTMLDivElement>(null);
  const measureRef = useRef<HTMLDivElement>(null);
  const groundRef = useRef<Api | null>(null);
  // Explicit, integer, square board size. chessground positions pieces and
  // highlights by pixel math (bounds.width / 8) but the CSS sizes squares at
  // 12.5% — if the rendered width is fractional the two disagree and pieces
  // drift off the square centers (worse toward the h-file / 1st rank as the
  // error accumulates). Flooring to a multiple of 8 forces both to resolve to
  // the same whole pixel per square. Mirrors ChessgroundBoard.tsx's explicit
  // pixel sizing.
  const [size, setSize] = useState<number>(0);
  const chessRef = useRef<Chess>(new Chess(puzzle.fen));
  /** Index into puzzle.moves of the next expected move. Even = team's turn. */
  const moveIndexRef = useRef<number>(0);
  const replyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const disabledRef = useRef<boolean>(!!disabled);
  // Latest callbacks / handler, held in refs to dodge stale closures in the
  // chessground event wiring (which is attached once at init).
  const onSolvedRef = useRef(onSolved);
  const onWrongRef = useRef(onWrong);
  const handleMoveRef = useRef<(orig: Key, dest: Key) => void>(() => {});
  onSolvedRef.current = onSolved;
  onWrongRef.current = onWrong;
  disabledRef.current = !!disabled;

  const orientation: 'white' | 'black' = orientationFromFen(puzzle.fen);

  /** Push the current chess.js position into chessground for the team to move. */
  const renderTeamTurn = () => {
    const chess = chessRef.current;
    const ground = groundRef.current;
    if (!ground) return;
    const history = chess.history({ verbose: true });
    const last = history[history.length - 1];
    ground.set({
      fen: chess.fen(),
      orientation,
      turnColor: orientation,
      lastMove: last ? [last.from as Key, last.to as Key] : undefined,
      check: chess.isCheck(),
      movable: {
        free: false,
        color: disabledRef.current ? undefined : orientation,
        dests: disabledRef.current ? new Map() : computeDests(chess),
      },
    });
  };

  const handleMove = (orig: Key, dest: Key) => {
    if (disabledRef.current) return;
    const chess = chessRef.current;
    const moves = puzzle.moves;
    const idx = moveIndexRef.current;

    // Outcome-based validation: accept the scripted move, or any legal move that
    // delivers mate on the finishing step (beginner positions have several).
    const decision = evaluateTeamMove(chess.fen(), moves, idx, orig, dest);

    // Wrong move: neither the scripted move nor an alternative mate. Snap back.
    if (!decision.accepted) {
      renderTeamTurn();
      onWrongRef.current();
      return;
    }

    // Correct: apply the team's move with the resolved promotion.
    chess.move({ from: orig, to: dest, promotion: decision.promotion });
    moveIndexRef.current = idx + 1;

    // Line finished, or the played move already mates → solved.
    if (decision.solved) {
      renderTeamTurn();
      onSolvedRef.current();
      return;
    }

    // Freeze, then auto-play the opponent's scripted reply.
    const history = chess.history({ verbose: true });
    const last = history[history.length - 1];
    groundRef.current?.set({
      fen: chess.fen(),
      turnColor: orientation === 'white' ? 'black' : 'white',
      lastMove: last ? [last.from as Key, last.to as Key] : undefined,
      check: chess.isCheck(),
      movable: { free: false, dests: new Map() },
    });

    replyTimerRef.current = setTimeout(() => {
      const reply = moves[moveIndexRef.current];
      if (!reply) return;
      chess.move({
        from: reply.slice(0, 2),
        to: reply.slice(2, 4),
        promotion: reply.length > 4 ? reply[4] : undefined,
      });
      moveIndexRef.current += 1;
      if (moveIndexRef.current >= moves.length) {
        renderTeamTurn();
        onSolvedRef.current();
      } else {
        renderTeamTurn();
      }
    }, OPPONENT_REPLY_DELAY);
  };
  handleMoveRef.current = handleMove;

  // Initialize chessground once the container has real dimensions.
  useEffect(() => {
    if (!elRef.current) return;
    let raf: number;
    let timer: ReturnType<typeof setTimeout>;

    const init = () => {
      const el = elRef.current;
      if (!el) return;
      const rect = el.getBoundingClientRect();
      if (rect.width > 0 && rect.height > 0) {
        groundRef.current = Chessground(el, {
          fen: chessRef.current.fen(),
          orientation,
          turnColor: orientation,
          coordinates: true,
          highlight: { lastMove: true, check: true },
          animation: { enabled: true, duration: 200 },
          draggable: { enabled: true, showGhost: true },
          selectable: { enabled: true },
          movable: {
            free: false,
            color: orientation,
            showDests: true,
            dests: computeDests(chessRef.current),
            events: { after: (orig, dest) => handleMoveRef.current(orig, dest) },
          },
        });
      } else {
        raf = requestAnimationFrame(init);
      }
    };
    timer = setTimeout(() => {
      raf = requestAnimationFrame(init);
    }, 10);

    return () => {
      clearTimeout(timer);
      cancelAnimationFrame(raf);
      if (replyTimerRef.current) clearTimeout(replyTimerRef.current);
      groundRef.current?.destroy();
      groundRef.current = null;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // Chessground memoizes the board's getBoundingClientRect() and only clears it
  // on window resize. A pure layout shift — content above the board (the rope
  // WebP, fonts) settling, or Android's dynamic-viewport `vh` reflow from the
  // URL bar — pushes the board down without firing a resize, leaving the cached
  // bounds stale. Taps then map one square off, so a correct (mating) tap lands
  // on an adjacent, non-mating square and is wrongly rejected. Re-measure on any
  // document-level layout change. Mirrors ChessgroundBoard.tsx.
  useEffect(() => {
    if (typeof ResizeObserver === 'undefined') return;
    const observer = new ResizeObserver(() => {
      groundRef.current?.redrawAll();
    });
    observer.observe(document.body);
    return () => observer.disconnect();
  }, []);

  // Measure the board's container and derive an integer, square size that is a
  // clean multiple of 8, so every square is a whole number of pixels and the
  // piece/highlight positions land exactly on the square centers. Recomputes on
  // any container resize (desktop panel, iPad split, mobile) — no breakpoints.
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

  // Recompute chessground's cached bounds whenever the integer size changes so
  // piece positions track the new dimensions exactly.
  useEffect(() => {
    if (size > 0) groundRef.current?.redrawAll();
  }, [size]);

  // Reset to a fresh puzzle whenever the puzzle identity changes.
  useEffect(() => {
    if (replyTimerRef.current) clearTimeout(replyTimerRef.current);
    chessRef.current = new Chess(puzzle.fen);
    moveIndexRef.current = 0;
    renderTeamTurn();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [puzzle.id]);

  // Freeze / unfreeze when the match ends.
  useEffect(() => {
    renderTeamTurn();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [disabled]);

  // measureRef is full-width (drives the size calc); the colored frame shrinks
  // to the exact integer board size so the ring hugs the board with no gap, and
  // the board element gets explicit width/height in pixels. lineHeight:0 kills
  // the inline-block descender gap that would otherwise make the box non-square.
  return (
    <div ref={measureRef} className="w-full flex justify-center">
      <div
        className={`rounded-xl overflow-hidden bg-white/5 ${FRAME[accent]}`}
        style={{ lineHeight: 0 }}
      >
        <div
          ref={elRef}
          style={{ width: size || undefined, height: size || undefined }}
        />
      </div>
    </div>
  );
}
