/**
 * Shared types for Tug of War (Milestone 1).
 */

/** A single puzzle. `moves` is the UCI solution line: the solving team plays the
 * moves at even indices (0, 2, …); odd indices are the opponent's auto-played
 * replies. A mate-in-1 has a single move; a mate-in-2 has three. */
export interface TugPuzzle {
  id: string;
  fen: string;
  moves: string[];
  rating: number;
  themes: string[];
}

export type TeamSide = 'A' | 'B';

export type GamePhase = 'setup' | 'match' | 'over';
