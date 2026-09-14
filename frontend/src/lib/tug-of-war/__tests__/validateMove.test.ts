import { describe, it, expect } from 'vitest';
import { Chess } from 'chess.js';
import { evaluateTeamMove } from '../validateMove';
import { TUG_PUZZLES } from '../puzzles';

/** All legal moves for the side to move in `fen`, as UCI strings. */
function legalMoves(fen: string): { from: string; to: string; mates: boolean }[] {
  const chess = new Chess(fen);
  return chess.moves({ verbose: true }).map((m) => {
    const probe = new Chess(fen);
    probe.move({ from: m.from, to: m.to, promotion: m.promotion ?? 'q' });
    return { from: m.from, to: m.to, mates: probe.isCheckmate() };
  });
}

describe('evaluateTeamMove — outcome-based validation', () => {
  it('accepts the scripted solution move for every puzzle', () => {
    for (const p of TUG_PUZZLES) {
      const uci = p.moves[0];
      const d = evaluateTeamMove(p.fen, p.moves, 0, uci.slice(0, 2), uci.slice(2, 4));
      expect(d.accepted, `${p.id} rejected its own scripted move`).toBe(true);
    }
  });

  it('accepts EVERY legal checkmate on a mate-in-1, not just the scripted one', () => {
    const mateIn1 = TUG_PUZZLES.filter((p) => p.moves.length === 1);
    expect(mateIn1.length).toBeGreaterThan(0);

    for (const p of mateIn1) {
      const moves = legalMoves(p.fen);
      const mates = moves.filter((m) => m.mates);
      expect(mates.length, `${p.id} should have >=1 mate`).toBeGreaterThan(0);

      for (const m of mates) {
        const d = evaluateTeamMove(p.fen, p.moves, 0, m.from, m.to);
        expect(d.accepted, `${p.id}: mate ${m.from}${m.to} was rejected`).toBe(true);
        expect(d.solved, `${p.id}: mate ${m.from}${m.to} not marked solved`).toBe(true);
      }
    }
  });

  it('rejects legal non-mating moves on a mate-in-1', () => {
    const mateIn1 = TUG_PUZZLES.filter((p) => p.moves.length === 1);
    for (const p of mateIn1) {
      for (const m of legalMoves(p.fen).filter((x) => !x.mates)) {
        const d = evaluateTeamMove(p.fen, p.moves, 0, m.from, m.to);
        expect(d.accepted, `${p.id}: non-mate ${m.from}${m.to} wrongly accepted`).toBe(false);
      }
    }
  });

  it('on a multi-move line, requires the scripted first move (so replies line up)', () => {
    const multi = TUG_PUZZLES.filter((p) => p.moves.length >= 3);
    for (const p of multi) {
      for (const m of legalMoves(p.fen)) {
        const played = `${m.from}${m.to}`;
        const d = evaluateTeamMove(p.fen, p.moves, 0, m.from, m.to);
        if (played === p.moves[0].slice(0, 4)) {
          expect(d.accepted, `${p.id}: scripted first move rejected`).toBe(true);
        } else {
          // A non-scripted first move must never be accepted (it isn't terminal).
          expect(d.accepted, `${p.id}: non-scripted first move ${played} accepted`).toBe(false);
        }
      }
    }
  });
});
