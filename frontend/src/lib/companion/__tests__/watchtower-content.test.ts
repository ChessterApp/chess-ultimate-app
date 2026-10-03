/**
 * @vitest-environment node
 *
 * Content validation (spec §16 step: machine-validate every task). Parses the
 * Phase 4 migration's Watchtower learning nodes (W01–W06) and asserts with
 * chess.js that every FEN is legal and every solution is consistent with the
 * position — move solutions are LEGAL from the FEN, square solutions name real
 * occupied squares. Hand-authored but machine-checked (not generated at runtime).
 */
import { describe, it, expect } from 'vitest';
import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';
import { Chess } from 'chess.js';
import { applyMove } from '@/lib/live-game/validate';
import { WATCHTOWER_NODE_FAMILIES } from '../review-rules';

const MIGRATION = resolve(
  __dirname,
  '../../../../../supabase/migrations/20261003_047_companion_watchtower_review.sql',
);

interface Node {
  family: string;
  fen: string;
  solution: { moves?: string[]; squares?: string[] };
  validator: string;
}

/** Extract the W01–W06 rows: family, FEN, solution JSONB, validator. */
function parseNodes(sql: string): Node[] {
  const nodes: Node[] = [];
  // Each VALUES tuple: '...', 'W0x', 'learning', '<FEN>', <3 prompts>, '<sol>'::jsonb, '<validator>', ...
  const re =
    /'(W0\d)',\s*'learning',\s*'([^']+)',[\s\S]*?'(\{[^']+\})'::jsonb,\s*'(move|squares|setup)'/g;
  let m: RegExpExecArray | null;
  while ((m = re.exec(sql)) !== null) {
    nodes.push({ family: m[1], fen: m[2], solution: JSON.parse(m[3]), validator: m[4] });
  }
  return nodes;
}

const sql = readFileSync(MIGRATION, 'utf8');
const nodes = parseNodes(sql);

describe('Watchtower content (W01–W06) — machine-validated', () => {
  it('ships exactly the six chapter nodes', () => {
    expect(nodes.map((n) => n.family).sort()).toEqual([...WATCHTOWER_NODE_FAMILIES]);
  });

  it.each(nodes.map((n) => [n.family, n] as const))('%s has a legal FEN', (_family, node) => {
    const chess = new Chess();
    expect(() => chess.load(node.fen)).not.toThrow();
  });

  it.each(nodes.map((n) => [n.family, n] as const))(
    '%s solution is consistent with the position',
    (_family, node) => {
      if (node.validator === 'move') {
        const moves = node.solution.moves ?? [];
        expect(moves.length).toBeGreaterThan(0);
        for (const uci of moves) {
          expect(applyMove(node.fen, uci).ok, `${uci} must be legal from ${node.fen}`).toBe(true);
        }
      } else if (node.validator === 'squares') {
        const squares = node.solution.squares ?? [];
        expect(squares.length).toBeGreaterThan(0);
        const chess = new Chess();
        chess.load(node.fen);
        for (const sq of squares) {
          expect(/^[a-h][1-8]$/.test(sq), `${sq} must be a real square`).toBe(true);
          // Attackers / defenders / the undefended target are all real pieces.
          expect(chess.get(sq as Parameters<typeof chess.get>[0]), `${sq} must hold a piece`).toBeTruthy();
        }
      } else {
        throw new Error(`unexpected validator ${node.validator}`);
      }
    },
  );
});
