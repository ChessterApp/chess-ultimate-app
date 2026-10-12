import { describe, it, expect } from 'vitest';
import { applyUci, judgeMove } from '../validate';
import { MATE1, MULTI, PROMO } from './fixtures';

/** Position after the setup move — where the user's first move is judged. */
const afterSetup = (p: { fen: string; moves: string[] }) => applyUci(p.fen, p.moves[0])!.fen;

describe('judgeMove', () => {
  it('exact expected move, non-final: correct + the opponent reply', () => {
    const v = judgeMove(afterSetup(MULTI), MULTI.moves, 1, 'e6e7');
    expect(v).toMatchObject({ kind: 'correct', reply: 'b2b1', from: 'e6', to: 'e7', uci: 'e6e7', capture: true });
  });

  it('the last move of the line solves it', () => {
    let fen = afterSetup(MULTI);
    for (const uci of MULTI.moves.slice(1, 5)) fen = applyUci(fen, uci)!.fen;
    expect(judgeMove(fen, MULTI.moves, 5, 'h6c1')).toMatchObject({ kind: 'solved', reply: null });
  });

  it('a wrong legal move is wrong (and still reports where it landed)', () => {
    const v = judgeMove(afterSetup(MULTI), MULTI.moves, 1, 'h6h7');
    expect(v).toMatchObject({ kind: 'wrong', to: 'h7', reply: null });
  });

  it('any checkmating move is accepted, not just the stored one', () => {
    expect(judgeMove(afterSetup(MATE1), MATE1.moves, 1, 'd1d8').kind).toBe('solved');
    expect(judgeMove(afterSetup(MATE1), MATE1.moves, 1, 'e1e8').kind).toBe('solved');
    expect(judgeMove(afterSetup(MATE1), MATE1.moves, 1, 'g1h1').kind).toBe('wrong');
  });

  it('promotion: explicit piece, omitted piece defaults to a queen, underpromotion judged as a move', () => {
    const fen = afterSetup(PROMO);
    expect(judgeMove(fen, PROMO.moves, 1, 'e7e8q')).toMatchObject({ kind: 'solved', uci: 'e7e8q' });
    expect(judgeMove(fen, PROMO.moves, 1, 'e7e8')).toMatchObject({ kind: 'solved', uci: 'e7e8q' });
    expect(judgeMove(fen, PROMO.moves, 1, 'e7e8r').kind).toBe('solved'); // also mate
    expect(judgeMove(fen, PROMO.moves, 1, 'e7e8n')).toMatchObject({ kind: 'wrong', uci: 'e7e8n' });
  });

  it('an illegal move is reported as such', () => {
    expect(judgeMove(afterSetup(MULTI), MULTI.moves, 1, 'h1h3').kind).toBe('illegal');
    expect(judgeMove(afterSetup(MULTI), MULTI.moves, 1, 'zz').kind).toBe('illegal');
  });

  it('castling compares as a move (e1g1)', () => {
    const fen = 'r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1';
    expect(judgeMove(fen, ['x', 'e1g1'], 1, 'e1g1').kind).toBe('solved');
  });
});

describe('applyUci', () => {
  it('returns null for an illegal move', () => {
    expect(applyUci(MULTI.fen, 'e2e4')).toBeNull();
  });
});
