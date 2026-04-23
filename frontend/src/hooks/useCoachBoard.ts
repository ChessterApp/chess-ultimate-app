import { useState, useCallback } from 'react';
import { Key } from 'chessground/types';
import { Chess } from 'chess.js';
import type {
  BoardAction,
  CoachBoardState,
  PuzzleState,
} from '@/types/coach';

const DEFAULT_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

interface UseCoachBoardReturn extends CoachBoardState {
  applyBoardAction: (action: BoardAction) => void;
  applyBoardActions: (actions: BoardAction[]) => void;
  nextMove: () => void;
  prevMove: () => void;
  firstMove: () => void;
  lastMove: () => void;
  validatePuzzleMove: (from: string, to: string) => 'correct' | 'wrong' | 'solved';
  resetBoard: () => void;
  setFenFromMove: (from: Key, to: Key) => void;
}

/**
 * Hook to manage the coach board state.
 * Handles board actions from the AI, move navigation, and puzzle validation.
 */
export function useCoachBoard(): UseCoachBoardReturn {
  const [fen, setFen] = useState(DEFAULT_FEN);
  const [pgn, setPgn] = useState('');
  const [moveIndex, setMoveIndex] = useState(-1);
  const [arrows, setArrows] = useState<Array<{ from: Key; to: Key; brush: string }>>([]);
  const [highlights, setHighlights] = useState<Key[]>([]);
  const [orientation, setOrientation] = useState<'white' | 'black'>('white');
  const [puzzleMode, setPuzzleMode] = useState(false);
  const [puzzleState, setPuzzleState] = useState<PuzzleState | null>(null);

  // Internal: list of FENs for PGN-loaded games (for navigation)
  const [pgnFens, setPgnFens] = useState<string[]>([]);

  const applyBoardAction = useCallback((action: BoardAction) => {
    switch (action.type) {
      case 'set_fen': {
        setFen(action.fen);
        setArrows([]);
        setHighlights([]);
        setPgnFens([]);
        setMoveIndex(-1);
        setPuzzleMode(false);
        setPuzzleState(null);
        break;
      }

      case 'load_pgn': {
        try {
          const chess = new Chess();
          chess.loadPgn(action.pgn);
          const history = chess.history({ verbose: true });

          // Build FEN list from PGN
          const fenList: string[] = [DEFAULT_FEN];
          const replay = new Chess();
          for (const move of history) {
            replay.move(move.san);
            fenList.push(replay.fen());
          }

          setPgn(action.pgn);
          setPgnFens(fenList);
          setMoveIndex(fenList.length - 1);
          setFen(fenList[fenList.length - 1]);
          setArrows([]);
          setHighlights([]);
          setPuzzleMode(false);
          setPuzzleState(null);
        } catch {
          // Invalid PGN, ignore
        }
        break;
      }

      case 'set_puzzle': {
        setFen(action.fen);
        setPuzzleMode(true);
        setPuzzleState({
          fen: action.fen,
          solution: action.solution,
          currentMoveIndex: 0,
          solved: false,
        });
        setArrows([]);
        setHighlights([]);
        setPgnFens([]);
        setMoveIndex(-1);
        break;
      }

      case 'draw_arrows': {
        setArrows(
          action.arrows.map((a) => ({
            from: a.from as Key,
            to: a.to as Key,
            brush: a.brush,
          }))
        );
        break;
      }

      case 'highlight_squares': {
        setHighlights(action.squares as Key[]);
        break;
      }

      case 'navigate': {
        if (pgnFens.length === 0) break;
        let newIndex = moveIndex;
        switch (action.direction) {
          case 'first':
            newIndex = 0;
            break;
          case 'prev':
            newIndex = Math.max(0, moveIndex - 1);
            break;
          case 'next':
            newIndex = Math.min(pgnFens.length - 1, moveIndex + 1);
            break;
          case 'last':
            newIndex = pgnFens.length - 1;
            break;
        }
        setMoveIndex(newIndex);
        setFen(pgnFens[newIndex]);
        break;
      }

      case 'flip_board': {
        setOrientation((prev) => (prev === 'white' ? 'black' : 'white'));
        break;
      }

      case 'clear_board': {
        setFen(DEFAULT_FEN);
        setPgn('');
        setPgnFens([]);
        setMoveIndex(-1);
        setArrows([]);
        setHighlights([]);
        setPuzzleMode(false);
        setPuzzleState(null);
        break;
      }
    }
  }, [pgnFens, moveIndex]);

  const applyBoardActions = useCallback(
    (actions: BoardAction[]) => {
      for (const action of actions) {
        applyBoardAction(action);
      }
    },
    [applyBoardAction]
  );

  const nextMove = useCallback(() => {
    if (pgnFens.length > 0 && moveIndex < pgnFens.length - 1) {
      const newIndex = moveIndex + 1;
      setMoveIndex(newIndex);
      setFen(pgnFens[newIndex]);
    }
  }, [pgnFens, moveIndex]);

  const prevMove = useCallback(() => {
    if (pgnFens.length > 0 && moveIndex > 0) {
      const newIndex = moveIndex - 1;
      setMoveIndex(newIndex);
      setFen(pgnFens[newIndex]);
    }
  }, [pgnFens, moveIndex]);

  const firstMove = useCallback(() => {
    if (pgnFens.length > 0) {
      setMoveIndex(0);
      setFen(pgnFens[0]);
    }
  }, [pgnFens]);

  const lastMove = useCallback(() => {
    if (pgnFens.length > 0) {
      const lastIndex = pgnFens.length - 1;
      setMoveIndex(lastIndex);
      setFen(pgnFens[lastIndex]);
    }
  }, [pgnFens]);

  const validatePuzzleMove = useCallback(
    (from: string, to: string): 'correct' | 'wrong' | 'solved' => {
      if (!puzzleState || puzzleState.solved) return 'wrong';

      const expectedMove = puzzleState.solution[puzzleState.currentMoveIndex];
      const uciMove = `${from}${to}`;

      if (uciMove === expectedMove) {
        const nextIndex = puzzleState.currentMoveIndex + 1;
        const isSolved = nextIndex >= puzzleState.solution.length;

        // Apply the move to the board
        try {
          const chess = new Chess(fen);
          chess.move({ from: from as any, to: to as any });
          setFen(chess.fen());
        } catch {
          // Move failed, but it was the right UCI move
        }

        setPuzzleState({
          ...puzzleState,
          currentMoveIndex: nextIndex,
          solved: isSolved,
        });

        return isSolved ? 'solved' : 'correct';
      }

      return 'wrong';
    },
    [puzzleState, fen]
  );

  const resetBoard = useCallback(() => {
    setFen(DEFAULT_FEN);
    setPgn('');
    setPgnFens([]);
    setMoveIndex(-1);
    setArrows([]);
    setHighlights([]);
    setPuzzleMode(false);
    setPuzzleState(null);
    setOrientation('white');
  }, []);

  const setFenFromMove = useCallback((from: Key, to: Key) => {
    try {
      const chess = new Chess(fen);
      chess.move({ from: from as string, to: to as string, promotion: 'q' });
      setFen(chess.fen());
    } catch {
      // Illegal move, ignore
    }
  }, [fen]);

  return {
    fen,
    pgn,
    moveIndex,
    arrows,
    highlights,
    orientation,
    puzzleMode,
    puzzleState,
    applyBoardAction,
    applyBoardActions,
    nextMove,
    prevMove,
    firstMove,
    lastMove,
    validatePuzzleMove,
    resetBoard,
    setFenFromMove,
  };
}
