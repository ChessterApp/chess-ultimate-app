'use client';

import React, { useRef, useEffect, useCallback, useState } from 'react';
import { Chessground as ChessgroundApi } from 'chessground';
import { Api } from 'chessground/api';
import { Config } from 'chessground/config';
import { Key, Color } from 'chessground/types';
import { Chess } from 'chess.js';
import 'chessground/assets/chessground.base.css';
import 'chessground/assets/chessground.brown.css';
import '@/styles/chessground-theme.css';
import { DEFAULT_BOARD_ANIMATION_DURATION } from '@/lib/setting/helper';

interface ChessgroundBoardProps {
  fen: string;
  orientation?: 'white' | 'black';
  onMove?: (from: Key, to: Key) => void;
  movable?: boolean;
  viewOnly?: boolean;
  arrows?: Array<{ from: Key; to: Key; brush: string }>;
  highlightSquares?: Key[];
  lastMove?: [Key, Key] | null;
  check?: boolean; // Auto-highlight king in check based on FEN
  boardSize?: number;
  animationDuration?: number;
  showCoordinates?: boolean;
  premovable?: boolean;
  onRightClick?: (key: Key) => void;
}

/**
 * React wrapper around chessground library
 * Provides a clean interface for chess board rendering with full chessground features
 */
export default function ChessgroundBoard({
  fen,
  orientation = 'white',
  onMove,
  movable = true,
  viewOnly = false,
  arrows = [],
  highlightSquares = [],
  lastMove = null,
  check = true, // Enable check highlighting by default
  boardSize,
  animationDuration = DEFAULT_BOARD_ANIMATION_DURATION,
  showCoordinates = true,
  premovable = false,
  onRightClick,
}: ChessgroundBoardProps) {
  const boardRef = useRef<HTMLDivElement>(null);
  const cgRef = useRef<Api | null>(null);

  // Maximum default size on roomy layouts (desktop). Container measurement
  // caps to this so the board never grows unbounded when placed in a wide,
  // definite-width container without an explicit boardSize.
  const MAX_DEFAULT_BOARD_SIZE = 520;

  // When no explicit boardSize is passed, size the board to fit its actual
  // parent container (measured with a ResizeObserver) rather than the raw
  // window width. This keeps the full board visible inside chrome (page
  // padding, card padding, board border) instead of clipping the right edge.
  // Callers that pass an explicit boardSize keep full control and are
  // unaffected.
  const [containerWidth, setContainerWidth] = useState<number | null>(null);

  useEffect(() => {
    if (boardSize !== undefined) return;
    if (typeof window === 'undefined' || typeof ResizeObserver === 'undefined') return;

    const el = boardRef.current?.parentElement;
    if (!el) return;

    const measure = () => setContainerWidth(el.clientWidth);
    measure();

    const observer = new ResizeObserver(measure);
    observer.observe(el);
    return () => observer.disconnect();
  }, [boardSize]);

  const responsiveBoardSize =
    containerWidth && containerWidth > 0
      ? Math.min(containerWidth, MAX_DEFAULT_BOARD_SIZE)
      : MAX_DEFAULT_BOARD_SIZE;

  const effectiveBoardSize = boardSize ?? responsiveBoardSize;

  const onMoveRef = useRef(onMove);
  onMoveRef.current = onMove;

  // Convert chess.js legal moves to chessground dests format
  const getLegalMoves = useCallback((fen: string): Map<Key, Key[]> => {
    try {
      const chess = new Chess(fen);
      const dests = new Map<Key, Key[]>();

      const squares = [
        'a8', 'b8', 'c8', 'd8', 'e8', 'f8', 'g8', 'h8',
        'a7', 'b7', 'c7', 'd7', 'e7', 'f7', 'g7', 'h7',
        'a6', 'b6', 'c6', 'd6', 'e6', 'f6', 'g6', 'h6',
        'a5', 'b5', 'c5', 'd5', 'e5', 'f5', 'g5', 'h5',
        'a4', 'b4', 'c4', 'd4', 'e4', 'f4', 'g4', 'h4',
        'a3', 'b3', 'c3', 'd3', 'e3', 'f3', 'g3', 'h3',
        'a2', 'b2', 'c2', 'd2', 'e2', 'f2', 'g2', 'h2',
        'a1', 'b1', 'c1', 'd1', 'e1', 'f1', 'g1', 'h1',
      ] as Key[];

      squares.forEach(square => {
        const moves = chess.moves({ square: square as any, verbose: true });
        if (moves.length > 0) {
          dests.set(square, moves.map(m => m.to as Key));
        }
      });

      return dests;
    } catch (err) {
      console.error('Error generating legal moves:', err);
      return new Map();
    }
  }, []);

  // Get current turn color from FEN
  const getTurnColor = useCallback((fen: string): Color => {
    const parts = fen.split(' ');
    return parts[1] === 'w' ? 'white' : 'black';
  }, []);

  // Detect if king is in check from FEN
  const isInCheck = useCallback((fen: string): Color | false => {
    try {
      const chess = new Chess(fen);
      if (chess.inCheck()) {
        return getTurnColor(fen);
      }
      return false;
    } catch {
      return false;
    }
  }, [getTurnColor]);

  // Initialize chessground
  useEffect(() => {
    if (!boardRef.current) return;

    const config: Config = {
      fen,
      orientation,
      viewOnly,

      movable: {
        free: false, // Only allow legal moves
        color: movable && !viewOnly ? getTurnColor(fen) : undefined,
        dests: movable && !viewOnly ? getLegalMoves(fen) : new Map(),
        showDests: true, // Show legal move indicators
        events: {
          after: (orig: Key, dest: Key) => {
            onMoveRef.current?.(orig, dest);
          },
        },
      },

      premovable: {
        enabled: premovable,
      },

      drawable: {
        enabled: true,
        visible: true,
        eraseOnClick: true,
        shapes: arrows.map(arrow => ({
          orig: arrow.from,
          dest: arrow.to,
          brush: arrow.brush,
        })),
      },

      highlight: {
        lastMove: true,
        check: true,
        custom: highlightSquares.length > 0 ? new Map(highlightSquares.map(sq => [sq, 'highlight'])) : undefined,
      },

      coordinates: showCoordinates,

      animation: {
        enabled: true,
        duration: animationDuration,
      },

      draggable: {
        enabled: movable && !viewOnly,
        showGhost: true,
      },

      selectable: {
        enabled: movable && !viewOnly,
      },

      events: {
        select: onRightClick,
      },
    };

    // Create chessground instance
    cgRef.current = ChessgroundApi(boardRef.current, config);

    // Set last move highlight
    if (lastMove) {
      cgRef.current.set({ lastMove });
    }

    // Cleanup on unmount
    return () => {
      cgRef.current?.destroy();
      cgRef.current = null;
    };
  }, []); // Only run on mount

  // Update position when FEN changes
  useEffect(() => {
    if (!cgRef.current) return;

    cgRef.current.set({
      fen,
      turnColor: getTurnColor(fen),
      movable: {
        color: movable && !viewOnly ? getTurnColor(fen) : undefined,
        dests: movable && !viewOnly ? getLegalMoves(fen) : new Map(),
      },
      draggable: {
        enabled: movable && !viewOnly,
        showGhost: true,
      },
      selectable: {
        enabled: movable && !viewOnly,
      },
      check: check ? isInCheck(fen) : false,
    });

    if (lastMove) {
      cgRef.current.set({ lastMove });
    }
  }, [fen, movable, viewOnly, check, lastMove, getLegalMoves, getTurnColor, isInCheck]);

  // Update orientation
  useEffect(() => {
    if (!cgRef.current) return;
    cgRef.current.set({ orientation });
  }, [orientation]);

  // Update arrows/shapes
  useEffect(() => {
    if (!cgRef.current) return;
    cgRef.current.setShapes(arrows.map(arrow => ({
      orig: arrow.from,
      dest: arrow.to,
      brush: arrow.brush,
    })));
  }, [arrows]);

  // Update square highlights
  useEffect(() => {
    if (!cgRef.current || highlightSquares.length === 0) return;

    cgRef.current.set({
      highlight: {
        lastMove: true,
        check: true,
        custom: new Map(highlightSquares.map(sq => [sq, 'highlight'])),
      },
    });
  }, [highlightSquares]);

  // Update animation duration
  useEffect(() => {
    if (!cgRef.current || !boardRef.current) return;
    cgRef.current.set({
      animation: {
        enabled: true,
        duration: animationDuration,
      },
    });
    // Also update the CSS variable
    (boardRef.current.style as any)['--cg-animation-duration'] = `${animationDuration}ms`;
  }, [animationDuration]);

  // Update coordinates visibility
  useEffect(() => {
    if (!cgRef.current) return;
    cgRef.current.set({ coordinates: showCoordinates });
  }, [showCoordinates]);

  return (
    <div
      ref={boardRef}
      className="chessground-board"
      style={{
        width: effectiveBoardSize,
        height: effectiveBoardSize,
        borderRadius: '2px',
        boxShadow: '0 2px 10px rgba(0,0,0,0.5)',
        ['--cg-animation-duration' as any]: `${animationDuration}ms`,
      }}
    />
  );
}
