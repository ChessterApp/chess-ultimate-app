import { useState, useCallback, useRef, useEffect } from 'react';
import { Key } from 'chessground/types';
import { Chess } from 'chess.js';
import type {
  BoardAction,
  CoachBoardState,
  PuzzleState,
} from '@/types/coach';

const DEFAULT_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

/**
 * Resolve one puzzle-solution move against a position. Hermes writes
 * solutions in SAN (board_control.py: "Solution moves in SAN"); the board
 * reports the played move as squares. Resolving both through chess.js lets
 * `Qxh7+`, `Qh7` and `d1h7` all match the same move.
 */
export function resolveSolutionMove(
  fen: string,
  notation: string,
): { from: string; to: string; san: string } | null {
  const text = (notation ?? '').trim();
  if (!text) return null;

  try {
    const move = new Chess(fen).move(text);
    return { from: move.from, to: move.to, san: move.san };
  } catch {
    // Not SAN for this position — try UCI.
  }

  const uci = text.toLowerCase();
  if (/^[a-h][1-8][a-h][1-8][qrbn]?$/.test(uci)) {
    try {
      const move = new Chess(fen).move({
        from: uci.slice(0, 2),
        to: uci.slice(2, 4),
        ...(uci[4] ? { promotion: uci[4] } : {}),
      });
      return { from: move.from, to: move.to, san: move.san };
    } catch {
      // Illegal in this position.
    }
  }

  return null;
}

interface UseCoachBoardReturn extends CoachBoardState {
  applyBoardAction: (action: BoardAction) => void;
  applyBoardActions: (actions: BoardAction[]) => void;
  nextMove: () => void;
  prevMove: () => void;
  firstMove: () => void;
  lastMove: () => void;
  validatePuzzleMove: (from: string, to: string) => 'correct' | 'wrong' | 'solved';
  resetBoard: () => void;
  setFenFromMove: (from: Key, to: Key, promotion?: 'q' | 'r' | 'b' | 'n') => void;
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

  // Internal: list of FENs for navigation (PGN-loaded games AND manual play)
  const [pgnFens, setPgnFens] = useState<string[]>([]);

  // Refs mirror the latest state so setFenFromMove can build history atomically
  // (no stale closures) even across rapid manual moves within a single tick.
  const fenRef = useRef(fen);
  const pgnFensRef = useRef(pgnFens);
  const moveIndexRef = useRef(moveIndex);
  useEffect(() => {
    fenRef.current = fen;
    pgnFensRef.current = pgnFens;
    moveIndexRef.current = moveIndex;
  }, [fen, pgnFens, moveIndex]);

  // Set position + history through the refs first: the coach's actions arrive
  // as one batch per turn (e.g. load_pgn followed by navigate), and the later
  // actions must see the history the earlier ones just built, not the closure.
  const commitHistory = useCallback((fens: string[], index: number) => {
    const safeIndex = Math.max(0, Math.min(index, fens.length - 1));
    fenRef.current = fens[safeIndex];
    pgnFensRef.current = fens;
    moveIndexRef.current = safeIndex;
    setPgnFens(fens);
    setMoveIndex(safeIndex);
    setFen(fens[safeIndex]);
  }, []);

  const applyBoardAction = useCallback((action: BoardAction) => {
    switch (action.type) {
      case 'set_fen': {
        commitHistory([action.fen], 0);
        setArrows([]);
        setHighlights([]);
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
          commitHistory(fenList, fenList.length - 1);
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
        commitHistory([action.fen], 0);
        setPuzzleMode(true);
        setPuzzleState({
          fen: action.fen,
          solution: action.solution,
          currentMoveIndex: 0,
          solved: false,
        });
        setArrows([]);
        setHighlights([]);
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
        const fens = pgnFensRef.current;
        const index = moveIndexRef.current;
        if (fens.length === 0) break;
        let newIndex = index;
        switch (action.direction) {
          case 'first':
            newIndex = 0;
            break;
          case 'prev':
            newIndex = Math.max(0, index - 1);
            break;
          case 'next':
            newIndex = Math.min(fens.length - 1, index + 1);
            break;
          case 'last':
            newIndex = fens.length - 1;
            break;
        }
        commitHistory(fens, newIndex);
        break;
      }

      case 'flip_board': {
        setOrientation((prev) => (prev === 'white' ? 'black' : 'white'));
        break;
      }

      case 'clear_board': {
        commitHistory([DEFAULT_FEN], 0);
        setPgn('');
        setArrows([]);
        setHighlights([]);
        setPuzzleMode(false);
        setPuzzleState(null);
        break;
      }
    }
  }, [commitHistory]);

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

      const expected = resolveSolutionMove(
        fen,
        puzzleState.solution[puzzleState.currentMoveIndex],
      );
      if (!expected || expected.from !== from || expected.to !== to) return 'wrong';

      const nextIndex = puzzleState.currentMoveIndex + 1;
      const isSolved = nextIndex >= puzzleState.solution.length;

      // Apply the resolved move (SAN carries the promotion piece, if any).
      try {
        const chess = new Chess(fen);
        chess.move(expected.san);
        commitHistory([...pgnFensRef.current.slice(0, moveIndexRef.current + 1), chess.fen()],
          moveIndexRef.current + 1);
      } catch {
        // Unreachable: the move was just resolved against this position.
      }

      setPuzzleState({
        ...puzzleState,
        currentMoveIndex: nextIndex,
        solved: isSolved,
      });

      return isSolved ? 'solved' : 'correct';
    },
    [puzzleState, fen, commitHistory]
  );

  const resetBoard = useCallback(() => {
    commitHistory([DEFAULT_FEN], 0);
    setPgn('');
    setArrows([]);
    setHighlights([]);
    setPuzzleMode(false);
    setPuzzleState(null);
    setOrientation('white');
  }, [commitHistory]);

  const setFenFromMove = useCallback((from: Key, to: Key, promotion?: 'q' | 'r' | 'b' | 'n') => {
    const baseFen = fenRef.current;
    let newFen: string;
    try {
      const chess = new Chess(baseFen);
      chess.move({ from: from as string, to: to as string, promotion: promotion ?? 'q' });
      newFen = chess.fen();
    } catch {
      // Illegal move, ignore
      return;
    }

    const prevFens = pgnFensRef.current;
    const prevIndex = moveIndexRef.current;

    let newFens: string[];
    if (prevFens.length === 0) {
      // No history yet: seed the pre-move position as the navigable base,
      // then append the new position.
      newFens = [baseFen, newFen];
    } else {
      // Truncate any forward history, then append the new position.
      newFens = [...prevFens.slice(0, prevIndex + 1), newFen];
    }
    const newIndex = newFens.length - 1;

    // Keep refs in sync synchronously so rapid successive moves see fresh values.
    fenRef.current = newFen;
    pgnFensRef.current = newFens;
    moveIndexRef.current = newIndex;

    setFen(newFen);
    setPgnFens(newFens);
    setMoveIndex(newIndex);
  }, []);

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
