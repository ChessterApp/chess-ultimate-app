import { describe, it, expect } from 'vitest';
import { Chess } from 'chess.js';
import { computeReachedFens, fenKey, STARTING_FEN } from '../useChessComExplorer';

const STARTING_KEY = fenKey(STARTING_FEN);

// FEN after 1. e4
const AFTER_E4 = new Chess();
AFTER_E4.move('e4');
const AFTER_E4_KEY = fenKey(AFTER_E4.fen());

// FEN after 1. e4 c5 (Sicilian)
const AFTER_E4_C5 = new Chess();
AFTER_E4_C5.move('e4');
AFTER_E4_C5.move('c5');
const AFTER_E4_C5_KEY = fenKey(AFTER_E4_C5.fen());

// FEN after 1. d4
const AFTER_D4 = new Chess();
AFTER_D4.move('d4');
const AFTER_D4_KEY = fenKey(AFTER_D4.fen());

describe('fenKey', () => {
  it('strips halfmove and fullmove counters', () => {
    const full = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';
    expect(fenKey(full)).toBe('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq -');
  });

  it('keeps the first four fields (placement, side, castling, ep)', () => {
    const key = fenKey(STARTING_FEN);
    expect(key.split(' ')).toHaveLength(4);
  });

  it('makes transposing positions compare equal regardless of move count', () => {
    // Same position reached by different move-order ends up with the same key
    // because halfmove/fullmove counters are dropped.
    const a = new Chess();
    a.move('e4'); a.move('e5'); a.move('Nf3'); a.move('Nc6');
    const b = new Chess();
    b.move('Nf3'); b.move('Nc6'); b.move('e4'); b.move('e5');
    expect(fenKey(a.fen())).toBe(fenKey(b.fen()));
  });
});

describe('computeReachedFens', () => {
  it('returns just the starting position for an empty PGN', () => {
    const fens = computeReachedFens('');
    expect(fens.has(STARTING_KEY)).toBe(true);
    expect(fens.size).toBe(1);
  });

  it('includes the starting position even for a non-empty PGN', () => {
    const fens = computeReachedFens('1. e4 c5');
    expect(fens.has(STARTING_KEY)).toBe(true);
  });

  it('collects every intermediate FEN reached by a PGN', () => {
    const fens = computeReachedFens('1. e4 c5 2. Nf3');
    expect(fens.has(STARTING_KEY)).toBe(true);
    expect(fens.has(AFTER_E4_KEY)).toBe(true);
    expect(fens.has(AFTER_E4_C5_KEY)).toBe(true);
  });

  it('does not include positions never reached', () => {
    const fens = computeReachedFens('1. e4 c5');
    expect(fens.has(AFTER_D4_KEY)).toBe(false);
  });

  it('handles a typical Chess.com PGN with headers', () => {
    const pgn = `[Event "Live Chess"]
[White "alice"]
[Black "bob"]
[Result "1-0"]

1. e4 c5 2. Nf3 d6 3. d4 cxd4 4. Nxd4 Nf6 1-0`;
    const fens = computeReachedFens(pgn);
    expect(fens.has(STARTING_KEY)).toBe(true);
    expect(fens.has(AFTER_E4_KEY)).toBe(true);
    expect(fens.has(AFTER_E4_C5_KEY)).toBe(true);
  });

  it('matches transposed positions when keyed by fenKey', () => {
    // Game A: 1. e4 e5 2. Nf3 Nc6
    // Game B: 1. Nf3 Nc6 2. e4 e5
    // Both reach the same final position; computeReachedFens must produce the
    // same final key for both.
    const a = computeReachedFens('1. e4 e5 2. Nf3 Nc6');
    const b = computeReachedFens('1. Nf3 Nc6 2. e4 e5');

    const finalA = new Chess();
    finalA.move('e4'); finalA.move('e5'); finalA.move('Nf3'); finalA.move('Nc6');
    const finalKey = fenKey(finalA.fen());

    expect(a.has(finalKey)).toBe(true);
    expect(b.has(finalKey)).toBe(true);
  });

  it('survives a malformed PGN without throwing', () => {
    const fens = computeReachedFens('this is not a real PGN @@@');
    // Should at least return the starting position as a safe fallback.
    expect(fens.has(STARTING_KEY)).toBe(true);
  });

  it('stops gracefully on a mid-game illegal move', () => {
    // chess.js loadPgn will reject the whole game on illegal moves, but the
    // function must not throw — it should fall back to the starting set.
    const fens = computeReachedFens('1. e4 e5 2. Qxq9');
    expect(fens.has(STARTING_KEY)).toBe(true);
  });
});

describe('position-filter pipeline (simulated)', () => {
  // Mirror the filter the component applies: keep games whose reachedFens set
  // contains the target FEN key. Skip filtering when at the starting position.
  function filterByPosition(
    games: Array<{ id: string; pgn: string }>,
    reachedFensMap: Map<string, Set<string>>,
    targetFen: string,
  ): Array<{ id: string; pgn: string }> {
    if (targetFen === STARTING_FEN) return games;
    const key = fenKey(targetFen);
    return games.filter((g) => reachedFensMap.get(g.id)?.has(key));
  }

  const games = [
    { id: 'g1', pgn: '1. e4 c5 2. Nf3' },             // Sicilian
    { id: 'g2', pgn: '1. e4 e5 2. Nf3 Nc6' },         // Open game
    { id: 'g3', pgn: '1. d4 d5 2. c4' },              // QGD
  ];

  const reachedFensMap = new Map<string, Set<string>>();
  for (const g of games) reachedFensMap.set(g.id, computeReachedFens(g.pgn));

  it('returns all games when fen === STARTING_FEN', () => {
    const result = filterByPosition(games, reachedFensMap, STARTING_FEN);
    expect(result).toHaveLength(3);
  });

  it('keeps only games that reached the Sicilian position', () => {
    const result = filterByPosition(games, reachedFensMap, AFTER_E4_C5.fen());
    expect(result.map((g) => g.id)).toEqual(['g1']);
  });

  it('keeps games whose PGN passes through 1.e4', () => {
    const result = filterByPosition(games, reachedFensMap, AFTER_E4.fen());
    expect(result.map((g) => g.id).sort()).toEqual(['g1', 'g2']);
  });

  it('returns zero games for a position none of them reached', () => {
    // After 1. d4 d5 2. Bf4 — not reached by any game in the set
    const exotic = new Chess();
    exotic.move('d4'); exotic.move('d5'); exotic.move('Bf4');
    const result = filterByPosition(games, reachedFensMap, exotic.fen());
    expect(result).toHaveLength(0);
  });
});
