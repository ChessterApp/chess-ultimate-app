/**
 * Chessground configuration for animated chess board
 */

import { Chess } from 'chess.js';
import type { Config } from 'chessground/config';
import type { Key } from 'chessground/types';

export interface ChessgroundConfigOptions {
  fen: string;
  onMove: (orig: Key, dest: Key) => void;
  orientation?: 'white' | 'black';
  movable?: boolean;
  premovable?: boolean;
  animationDuration?: number;
  /** Show legal-move dots after selecting a piece (dests computed from the FEN) */
  showLegalDests?: boolean;
}

/**
 * Legal destinations per square for the side to move, in chessground's dests
 * shape. Returns undefined when chess.js rejects the FEN (lesson positions
 * without kings etc.), so the board falls back to free moves without dots.
 */
export function computeLegalDests(fen: string): Map<Key, Key[]> | undefined {
  let chess: Chess;
  try {
    chess = new Chess(fen);
  } catch {
    return undefined;
  }
  const dests = new Map<Key, Key[]>();
  for (const m of chess.moves({ verbose: true })) {
    const from = m.from as Key;
    dests.set(from, [...(dests.get(from) ?? []), m.to as Key]);
  }
  return dests;
}

/**
 * Get Chessground configuration for beginner-friendly board
 */
export function getChessgroundConfig({
  fen,
  onMove,
  orientation = 'white',
  movable = true,
  premovable = false,
  animationDuration = 50,
  showLegalDests = false,
}: ChessgroundConfigOptions): Config {
  return {
    fen,
    orientation,
    turnColor: orientation,

    // Movement settings
    movable: {
      free: true, // Allow free movement (we'll validate in the move handler)
      color: orientation, // Allow moving pieces for the current orientation
      // Free moves stay allowed (validated in the move handler); dests only draw the dots
      showDests: showLegalDests,
      dests: showLegalDests ? computeLegalDests(fen) : undefined,
      events: {
        after: onMove,
      },
    },

    // Disable premoves for beginners
    premovable: {
      enabled: premovable,
    },

    // Enable drawable for auto-shapes (hints), but disable user drawing
    drawable: {
      enabled: true,
      visible: true,
      eraseOnClick: false,
      // User cannot draw shapes manually (only via setAutoShapes API)
      shapes: [],
      autoShapes: [],
    },

    // Visual settings
    highlight: {
      lastMove: true, // Highlight last move
      check: true, // Highlight king in check
    },

    // Show coordinates (a-h, 1-8)
    coordinates: true,

    // Animation settings
    animation: {
      enabled: true,
      duration: animationDuration,
    },

    // Drag settings
    draggable: {
      enabled: movable,
      showGhost: true, // Show ghost piece while dragging
    },

    // Disable auto-castle and auto-promote for explicit control
    selectable: {
      enabled: true,
    },
  };
}

/**
 * Get board theme CSS class
 */
export function getBoardThemeClass(theme: 'brown' | 'blue' | 'green' = 'brown'): string {
  return `board-theme-${theme}`;
}

/**
 * Get piece set path
 */
export function getPieceSetPath(pieceSet: 'alpha' | 'cburnett' = 'alpha'): string {
  return `/pieces/${pieceSet}`;
}
