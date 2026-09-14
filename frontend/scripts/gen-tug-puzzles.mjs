// One-off generator: produce guaranteed-legal mate-in-1 and forced mate-in-2
// positions for the Tug of War puzzle set, then WRITE src/lib/tug-of-war/puzzles.ts.
//
// Run:  node scripts/gen-tug-puzzles.mjs
//
// Approach: an earlier version brute-forced every (king, king, piece, square)
// combination calling chess.js isCheckmate() on each — that never finished
// (~10ms/position × 70k+ positions). This version instead builds a handful of
// textbook beginner mates by formula, then multiplies them with the 8 board
// symmetries (rotations + reflections), which preserve checkmate for these
// pawnless positions. chess.js is called only to VERIFY each finished candidate
// (one isCheckmate() per line), so the whole generator runs in well under 1s.
// Every shipped puzzle is re-verified by __tests__/puzzles.test.ts.
import { Chess } from 'chess.js';
import { writeFileSync } from 'node:fs';
import { fileURLToPath } from 'node:url';
import { dirname, join } from 'node:path';

const FILES = 'abcdefgh';
const name = (f, r) => FILES[f] + (r + 1);        // (0..7,0..7) -> algebraic
const coord = (s) => [FILES.indexOf(s[0]), +s[1] - 1];

// Build + validate a white-to-move FEN from a { square: piece } map.
function makeFen(pieces) {
  const board = Array.from({ length: 8 }, () => Array(8).fill(''));
  for (const [square, pc] of Object.entries(pieces)) {
    const [f, r] = coord(square);
    board[r][f] = pc;
  }
  const rows = [];
  for (let r = 7; r >= 0; r--) {
    let row = '', empty = 0;
    for (let f = 0; f < 8; f++) {
      if (board[r][f]) { if (empty) { row += empty; empty = 0; } row += board[r][f]; }
      else empty++;
    }
    if (empty) row += empty;
    rows.push(row);
  }
  return rows.join('/') + ' w - - 0 1';
}

// The 8 dihedral symmetries of the board, each as a coordinate map (f,r)->(f,r).
const SYMMETRIES = [
  ([f, r]) => [f, r],           // identity
  ([f, r]) => [7 - f, r],       // horizontal flip
  ([f, r]) => [f, 7 - r],       // vertical flip
  ([f, r]) => [7 - f, 7 - r],   // rotate 180
  ([f, r]) => [r, f],           // transpose (a1-h8 diagonal)
  ([f, r]) => [7 - r, 7 - f],   // anti-transpose
  ([f, r]) => [r, 7 - f],       // rotate 90
  ([f, r]) => [7 - r, f],       // rotate 270
];

const applySymSquare = (sym, square) => { const [f, r] = sym(coord(square)); return name(f, r); };
const applySymUci = (sym, uci) =>
  applySymSquare(sym, uci.slice(0, 2)) + applySymSquare(sym, uci.slice(2, 4)) + (uci.slice(4) || '');

// A "base" is a piece map (white to move) plus the UCI solution line. Verify a
// concrete base/variant with chess.js: legal FEN, white to move, black not
// already in check, every move legal, forced single reply on mate-in-2, and the
// line ends in checkmate. Returns { fen, moves } or null.
function verify(pieces, moves) {
  const fen = makeFen(pieces);
  let c;
  try { c = new Chess(fen); } catch { return null; }
  if (c.turn() !== 'w' || c.isCheck()) return null;
  for (let i = 0; i < moves.length; i++) {
    const uci = moves[i];
    const legal = c.moves({ verbose: true }).find(
      (m) => m.from === uci.slice(0, 2) && m.to === uci.slice(2, 4),
    );
    if (!legal) return null;
    // On a mate-in-2, black's reply (index 1) must be the ONLY legal move so the
    // puzzle is genuinely forced.
    if (i === 1 && c.moves().length !== 1) return null;
    c.move({ from: uci.slice(0, 2), to: uci.slice(2, 4), promotion: uci.slice(4) || undefined });
  }
  return c.isCheckmate() ? { fen, moves } : null;
}

// Expand a base into all 8 symmetric variants, keep the ones that verify, dedup
// by FEN.
function expand(pieces, moves, seen) {
  const out = [];
  for (const sym of SYMMETRIES) {
    const p = {};
    for (const [sq, pc] of Object.entries(pieces)) p[applySymSquare(sym, sq)] = pc;
    const mv = moves.map((m) => applySymUci(sym, m));
    const v = verify(p, mv);
    if (v && !seen.has(v.fen)) { seen.add(v.fen); out.push(v); }
  }
  return out;
}

// --- Queen "kiss" mate-in-1: BK on the 8th rank, WK two ranks behind on the
// same file, queen slides along the 7th rank to sit in front of the king. ---
function queenMates() {
  const seen = new Set();
  const all = [];
  for (let bf = 0; bf < 8; bf++) {
    const bk = name(bf, 7);            // black king, 8th rank
    const wk = name(bf, 5);            // white king, 6th rank (supports the queen)
    const target = name(bf, 6);        // queen's mating square, 7th rank
    const srcF = bf <= 3 ? 7 : 0;      // queen source on the far side of the 7th rank
    const src = name(srcF, 6);
    if (src === target) continue;
    all.push(...expand({ [bk]: 'k', [wk]: 'K', [src]: 'Q' }, [src + target], seen));
  }
  return all;
}

// --- Rook back-rank mate-in-1: BK on the 8th rank in opposition to WK, rook
// swings up a file to check along the back rank. ---
function rookMates() {
  const seen = new Set();
  const all = [];
  for (let bf = 0; bf < 8; bf++) {
    const bk = name(bf, 7);
    const wk = name(bf, 5);
    const tf = bf <= 3 ? 7 : 0;        // rook checks from the far corner of the 8th rank
    if (tf === bf) continue;
    const target = name(tf, 7);
    const src = name(tf, 0);           // rook starts on the 1st rank of that file
    all.push(...expand({ [bk]: 'k', [wk]: 'K', [src]: 'R' }, [src + target], seen));
  }
  return all;
}

// --- Forced mate-in-2: king boxed in the corner, a quiet 7th-rank queen move
// leaves exactly one legal reply, then the queen mates. ---
function mate2s() {
  const seen = new Set();
  // BK a8, WK a6, WQ e1 -> Qe7 (only Kb8) -> Qb7#.
  return expand({ a8: 'k', a6: 'K', e1: 'Q' }, ['e1e7', 'a8b8', 'e7b7'], seen);
}

const q = queenMates();
const r = rookMates();
const m2 = mate2s();
console.error(`unique variants: queen=${q.length} rook=${r.length} mate2=${m2.length}`);

// Assemble the typed puzzle list.
const puzzles = [];
let n = 0;
const pad = (i) => String(i).padStart(3, '0');
const take = (arr, count, prefix, rating, themes) => {
  for (const p of arr.slice(0, count)) {
    puzzles.push({ id: `tug-${prefix}-${pad(++n)}`, fen: p.fen, moves: p.moves, rating, themes });
  }
};
take(q, 26, 'q1', 500, ['mateIn1', 'queenMate']);
take(r, 14, 'r1', 650, ['mateIn1', 'rookMate']);
take(m2, 8, 'm2', 900, ['mateIn2', 'queenMate']);

if (puzzles.length < 40) {
  console.error(`ERROR: only ${puzzles.length} puzzles generated (<40)`);
  process.exit(1);
}

const header = `/**
 * Tug of War (Milestone 1) puzzle data set.
 *
 * GENERATED by scripts/gen-tug-puzzles.mjs — do not edit by hand; re-run the
 * generator instead. Every position is a legal white-to-move checkmate that was
 * verified with chess.js at generation time and is re-verified by
 * __tests__/puzzles.test.ts. Deliberately easy (K+Q / K+R vs K) so beginners at
 * the Pawn/Knight rating band can solve them.
 */
import type { TugPuzzle } from './types';

export const TUG_PUZZLES: TugPuzzle[] = ${JSON.stringify(puzzles, null, 2)};
`;

const outPath = join(dirname(fileURLToPath(import.meta.url)), '..', 'src', 'lib', 'tug-of-war', 'puzzles.ts');
writeFileSync(outPath, header);
console.error(`wrote ${puzzles.length} puzzles to ${outPath}`);
