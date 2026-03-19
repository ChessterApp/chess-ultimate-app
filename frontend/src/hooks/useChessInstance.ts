import { useState, useEffect } from 'react';
import type { Chess } from 'chess.js';

/**
 * Hook to lazily load and initialize a Chess instance on the client side.
 * This avoids SSR issues with chess.js by loading it only in the browser.
 *
 * @param initialFen - Optional FEN string to initialize the chess instance
 * @returns Chess instance or null if not yet loaded
 */
export function useChessInstance(initialFen?: string): Chess | null {
  const [chess, setChess] = useState<Chess | null>(null);

  useEffect(() => {
    // Dynamically import chess.js only on the client side
    import('chess.js').then(({ Chess }) => {
      setChess(new Chess(initialFen));
    });
  }, [initialFen]);

  return chess;
}

/**
 * Hook to get the Chess constructor for creating multiple instances.
 * This is useful when you need to create Chess instances dynamically.
 *
 * @returns Chess constructor or null if not yet loaded
 */
export function useChessConstructor(): typeof Chess | null {
  const [ChessConstructor, setChessConstructor] = useState<typeof Chess | null>(null);

  useEffect(() => {
    // Dynamically import chess.js only on the client side
    import('chess.js').then(({ Chess }) => {
      setChessConstructor(() => Chess);
    });
  }, []);

  return ChessConstructor;
}
