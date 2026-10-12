import type { RushPuzzle } from '../types';

/** Lichess 00008: setup f2g3, then e6e7 b2b1 b3c1 b1c1 h6c1 (user plays White). */
export const MULTI: RushPuzzle = {
  index: 0,
  id: '00008',
  fen: 'r6k/pp2r2p/4Rp1Q/3p4/8/1N1P2R1/PqP2bPP/7K b - - 0 24',
  moves: ['f2g3', 'e6e7', 'b2b1', 'b3c1', 'b1c1', 'h6c1'],
  rating: 1797,
  themes: ['crushing', 'hangingPiece', 'long', 'middlegame'],
  color: 'white',
};

/** Lichess 000aY: setup g5e7, then a5c3 b2c3 c6e7 (user plays Black). */
export const NEXT: RushPuzzle = {
  index: 1,
  id: '000aY',
  fen: 'r4rk1/pp3ppp/2n1b3/q1pp2B1/8/P1Q2NP1/1PP1PP1P/2KR3R w - - 0 15',
  moves: ['g5e7', 'a5c3', 'b2c3', 'c6e7'],
  rating: 1412,
  themes: ['advantage', 'master', 'middlegame', 'short'],
  color: 'black',
};

/** Mate in 1: the line says Rd8#, but Re8# mates too (§7.4 any mate counts). */
export const MATE1: RushPuzzle = {
  index: 0,
  id: 'MATE1',
  fen: '6k1/p4ppp/8/8/8/8/5PPP/3RR1K1 b - - 0 1',
  moves: ['a7a6', 'd1d8'],
  rating: 400,
  themes: ['mate', 'mateIn1'],
  color: 'white',
};

/** Promotion mate: e8=Q# (e8=R# also mates; e8=N is just wrong). */
export const PROMO: RushPuzzle = {
  index: 0,
  id: 'PROMO',
  fen: '6k1/4P3/6K1/8/8/8/8/r7 b - - 0 1',
  moves: ['a1a2', 'e7e8q'],
  rating: 600,
  themes: ['mate', 'promotion'],
  color: 'white',
};

/** A pack of `n` mate-in-1s (index 0..n-1), solved by d1d8, failed by g1h1. */
export function matePack(n: number, from = 0): RushPuzzle[] {
  return Array.from({ length: n }, (_, i) => ({
    ...MATE1, index: from + i, id: `M${from + i}`, rating: 400 + 45 * (from + i),
  }));
}

export const SOLVE = 'd1d8';
export const MISS = 'g1h1';
