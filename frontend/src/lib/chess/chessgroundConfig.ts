/**
 * Chessground configuration for animated chess board
 */

import type { Config } from 'chessground/config';
import type { Key } from 'chessground/types';

export interface ChessgroundConfigOptions {
  fen: string;
  onMove: (orig: Key, dest: Key) => void;
  orientation?: 'white' | 'black';
  movable?: boolean;
  premovable?: boolean;
  animationDuration?: number;
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
}: ChessgroundConfigOptions): Config {
  return {
    fen,
    orientation,

    // Movement settings
    movable: {
      free: true, // Allow free movement (we'll validate in the move handler)
      color: orientation, // Allow moving pieces for the current orientation
      showDests: false, // We'll show hints manually via the Hint button
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
