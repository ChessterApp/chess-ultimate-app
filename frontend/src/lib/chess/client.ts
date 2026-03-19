/**
 * Client-side-only chess.js wrapper
 *
 * This module dynamically imports chess.js to ensure it's only loaded
 * in the browser, avoiding any potential SSR issues.
 *
 * Usage:
 * ```ts
 * import { getChess } from '@/lib/chess/client';
 *
 * // In a useEffect or event handler (not at module level):
 * const { Chess } = await getChess();
 * const game = new Chess();
 * ```
 */

let chessModule: typeof import('chess.js') | null = null;

/**
 * Get the chess.js module, loading it dynamically if not already loaded.
 * This ensures chess.js is only loaded client-side.
 *
 * @returns Promise that resolves to the chess.js module
 */
export async function getChess() {
  if (!chessModule) {
    chessModule = await import('chess.js');
  }
  return chessModule;
}

/**
 * Create a new Chess instance.
 * Convenience wrapper around getChess() for common use case.
 *
 * @param fen - Optional FEN string to initialize the chess instance
 * @returns Promise that resolves to a new Chess instance
 */
export async function createChess(fen?: string) {
  const { Chess } = await getChess();
  return new Chess(fen);
}

// Re-export types for convenience
export type { Chess, Square, Move, Color, PieceSymbol, Piece } from 'chess.js';
