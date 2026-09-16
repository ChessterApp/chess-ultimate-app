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
    // Classify by theme, not move count: single-move tactics (e.g. pins) are
    // also length-1 but do not deliver mate.
    const mateIn1 = TUG_PUZZLES.filter((p) => p.themes.includes('mateIn1'));
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
    const mateIn1 = TUG_PUZZLES.filter((p) => p.themes.includes('mateIn1'));
    for (const p of mateIn1) {
      for (const m of legalMoves(p.fen).filter((x) => !x.mates)) {
        const d = evaluateTeamMove(p.fen, p.moves, 0, m.from, m.to);
        expect(d.accepted, `${p.id}: non-mate ${m.from}${m.to} wrongly accepted`).toBe(false);
      }
    }
  });

  it('on a multi-move line, a non-mating first move must follow the script', () => {
    const multi = TUG_PUZZLES.filter((p) => p.moves.length >= 3);
    for (const p of multi) {
      for (const m of legalMoves(p.fen)) {
        const played = `${m.from}${m.to}`;
        const d = evaluateTeamMove(p.fen, p.moves, 0, m.from, m.to);
        if (played === p.moves[0].slice(0, 4)) {
          expect(d.accepted, `${p.id}: scripted first move rejected`).toBe(true);
        } else if (m.mates) {
          // A faster mate is always a win, even on a non-terminal ply.
          expect(d.accepted, `${p.id}: faster mate ${played} rejected`).toBe(true);
          expect(d.solved, `${p.id}: faster mate ${played} not solved`).toBe(true);
        } else {
          // A non-scripted, non-mating first move must not be accepted.
          expect(d.accepted, `${p.id}: non-scripted first move ${played} accepted`).toBe(false);
        }
      }
    }
  });

  it('accepts a mate-in-1 shortcut on a position mislabeled as mate-in-2', () => {
    // BK a8, WK c8, WQ h4 — scripted as mate-in-2 (Qb4, Ka7, Qb7#) but Qa4# is an
    // immediate mate. This is the exact bug users hit ("...Qa4" flagged wrong).
    const fen = 'k1K5/8/8/8/7Q/8/8/8 w - - 0 1';
    const scripted = ['h4b4', 'a8a7', 'b4b7'];

    // The mate-in-1 shortcut on the FIRST (non-terminal) ply is accepted + solved.
    const shortcut = evaluateTeamMove(fen, scripted, 0, 'h4', 'a4');
    expect(shortcut.accepted, 'Qa4# shortcut rejected').toBe(true);
    expect(shortcut.solved, 'Qa4# shortcut not marked solved').toBe(true);

    // The scripted quiet first move still works (it does not mate, so not solved).
    const quiet = evaluateTeamMove(fen, scripted, 0, 'h4', 'b4');
    expect(quiet.accepted, 'scripted Qb4 rejected').toBe(true);
    expect(quiet.solved, 'scripted Qb4 wrongly marked solved').toBe(false);

    // A non-scripted, non-mating first move is still rejected.
    const wrong = evaluateTeamMove(fen, scripted, 0, 'c8', 'c7');
    expect(wrong.accepted, 'non-mating non-scripted move accepted').toBe(false);
  });
});
