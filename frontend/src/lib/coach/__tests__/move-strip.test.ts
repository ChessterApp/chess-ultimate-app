import { describe, it, expect } from 'vitest';
import { Chess } from 'chess.js';
import { sanMoves } from '../move-strip';

function fensOf(sans: string[]): string[] {
  const chess = new Chess();
  const fens = [chess.fen()];
  for (const san of sans) {
    chess.move(san);
    fens.push(chess.fen());
  }
  return fens;
}

describe('sanMoves', () => {
  it('recovers the moves between consecutive positions', () => {
    const moves = ['e4', 'c5', 'Nf3', 'd6', 'd4', 'cxd4', 'Nxd4', 'Nf6', 'Nc3'];
    expect(sanMoves(fensOf(moves))).toEqual(moves);
  });

  it('handles castling and promotion', () => {
    const chess = new Chess('4k3/1P6/8/8/8/8/8/4K2R w K - 0 1');
    const fens = [chess.fen()];
    chess.move('O-O');
    fens.push(chess.fen());
    chess.move('Kd7');
    fens.push(chess.fen());
    chess.move('b8=Q');
    fens.push(chess.fen());
    expect(sanMoves(fens)).toEqual(['O-O', 'Kd7', 'b8=Q']);
  });

  it('is empty for a single position or none', () => {
    expect(sanMoves([])).toEqual([]);
    expect(sanMoves([new Chess().fen()])).toEqual([]);
  });

  it('stops at a jump no legal move explains', () => {
    const fens = fensOf(['e4']);
    fens.push('8/8/8/4k3/8/8/8/4K3 w - - 0 1');
    expect(sanMoves(fens)).toEqual(['e4']);
  });
});
