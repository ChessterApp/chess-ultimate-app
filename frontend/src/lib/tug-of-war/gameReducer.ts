/**
 * Tug of War game reducer (Milestone 1).
 *
 * Pure, side-effect-free game state. The board components report only two
 * outcomes per team — a full solve or a single wrong move — and this reducer
 * owns scoring, the 3-wrong auto-skip rule, the rope differential clamp and win
 * detection. Keeping it pure makes the whole game loop unit-testable without a
 * DOM or chess engine.
 */

import type { TugPuzzle, TeamSide, GamePhase } from './types';

/** Rope differential is clamped to this range; reaching either end wins. */
export const ROPE_LIMIT = 5;
/** Wrong moves allowed on one puzzle before it is auto-skipped. */
export const MAX_WRONG_ATTEMPTS = 3;

export interface BoardState {
  /** This team's disjoint puzzle list, fixed for the match. */
  puzzles: TugPuzzle[];
  /** Pointer into `puzzles`; the current puzzle is `puzzles[index % length]`. */
  index: number;
  /** Wrong moves on the current puzzle so far (0..MAX_WRONG_ATTEMPTS). */
  wrongAttempts: number;
  /** Total puzzles this team has solved. */
  solved: number;
  /** Increments each time this board auto-skips a puzzle (drives the toast). */
  skips: number;
}

export interface GameState {
  phase: GamePhase;
  teamAName: string;
  teamBName: string;
  boardA: BoardState;
  boardB: BoardState;
  /** teamA solves − teamB solves, clamped to ±ROPE_LIMIT. */
  rope: number;
  winner: TeamSide | null;
}

export type GameAction =
  | {
      type: 'START_MATCH';
      teamAName: string;
      teamBName: string;
      queueA: TugPuzzle[];
      queueB: TugPuzzle[];
    }
  | { type: 'SOLVE'; team: TeamSide }
  | { type: 'WRONG'; team: TeamSide }
  | { type: 'REMATCH' };

const clamp = (n: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, n));

/** The puzzle currently shown on a board. */
export function currentPuzzle(board: BoardState): TugPuzzle | null {
  if (board.puzzles.length === 0) return null;
  return board.puzzles[board.index % board.puzzles.length];
}

function makeBoard(puzzles: TugPuzzle[]): BoardState {
  return { puzzles, index: 0, wrongAttempts: 0, solved: 0, skips: 0 };
}

export function initialState(
  teamAName = 'Knights',
  teamBName = 'Rooks',
): GameState {
  return {
    phase: 'setup',
    teamAName,
    teamBName,
    boardA: makeBoard([]),
    boardB: makeBoard([]),
    rope: 0,
    winner: null,
  };
}

export function gameReducer(state: GameState, action: GameAction): GameState {
  switch (action.type) {
    case 'START_MATCH': {
      return {
        phase: 'match',
        teamAName: action.teamAName.trim() || 'Knights',
        teamBName: action.teamBName.trim() || 'Rooks',
        boardA: makeBoard(action.queueA),
        boardB: makeBoard(action.queueB),
        rope: 0,
        winner: null,
      };
    }

    case 'SOLVE': {
      if (state.phase !== 'match') return state;
      const key = action.team === 'A' ? 'boardA' : 'boardB';
      const board = state[key];
      const nextBoard: BoardState = {
        ...board,
        index: board.index + 1,
        wrongAttempts: 0,
        solved: board.solved + 1,
      };
      const solvedA = action.team === 'A' ? nextBoard.solved : state.boardA.solved;
      const solvedB = action.team === 'B' ? nextBoard.solved : state.boardB.solved;
      const diff = solvedA - solvedB;
      const rope = clamp(diff, -ROPE_LIMIT, ROPE_LIMIT);
      let phase: GamePhase = 'match';
      let winner: TeamSide | null = null;
      if (diff >= ROPE_LIMIT) {
        phase = 'over';
        winner = 'A';
      } else if (diff <= -ROPE_LIMIT) {
        phase = 'over';
        winner = 'B';
      }
      return { ...state, [key]: nextBoard, rope, phase, winner };
    }

    case 'WRONG': {
      if (state.phase !== 'match') return state;
      const key = action.team === 'A' ? 'boardA' : 'boardB';
      const board = state[key];
      const attempts = board.wrongAttempts + 1;
      // Wrong moves never touch the rope or score.
      if (attempts >= MAX_WRONG_ATTEMPTS) {
        // Discard the current puzzle and advance to the next one.
        const nextBoard: BoardState = {
          ...board,
          index: board.index + 1,
          wrongAttempts: 0,
          skips: board.skips + 1,
        };
        return { ...state, [key]: nextBoard };
      }
      return { ...state, [key]: { ...board, wrongAttempts: attempts } };
    }

    case 'REMATCH': {
      // Back to setup, preserving team names; queues are rebuilt on next start.
      return initialState(state.teamAName, state.teamBName);
    }

    default:
      return state;
  }
}
