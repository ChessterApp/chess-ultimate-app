import { describe, it, expect } from 'vitest';
import { gameViewFromBoard } from '../game-restore';
import type { BoardRecord } from '../boards-api';

// Seam audit 28.10: a reload during a game against the coach lost the kept side lines and the check flag.
function liveBoard(fen: string, moves: string[], gameState: Record<string, unknown> = {}): BoardRecord {
  return {
    id: 'g1',
    session_id: 's1',
    kind: 'game',
    title: 'You — Coach',
    pgn: moves.join(' '),
    fen,
    ply: moves.length,
    orientation: 'white',
    annotations: {},
    game_state: { status: 'playing', student_color: 'white', engine_elo: 1200, moves, variations: [], ...gameState },
    created_at: 0,
    updated_at: 0,
  };
}

describe('gameViewFromBoard', () => {
  it('keeps the side lines Hermes stored with the game', () => {
    const view = gameViewFromBoard(
      liveBoard('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2', ['e4', 'e5'], {
        variations: [{ at_ply: 1, moves: ['c5', 'Nf3'], at: 1790000000 }],
      }),
    );
    expect(view?.variations).toEqual([{ at_ply: 1, moves: ['c5', 'Nf3'] }]);
  });

  it('drops a malformed side line instead of failing the restore', () => {
    const view = gameViewFromBoard(
      liveBoard('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2', ['e4', 'e5'], {
        variations: [{ at_ply: 'x', moves: 'c5' }, null, { at_ply: 0, moves: ['d4'] }],
      }),
    );
    expect(view?.variations).toEqual([{ at_ply: 0, moves: ['d4'] }]);
  });

  it('knows the side to move is in check', () => {
    // 1.e4 f5 2.Qh5+ — Black (the student) is in check.
    const view = gameViewFromBoard(
      liveBoard('rnbqkbnr/ppppp1pp/8/5p1Q/4P3/8/PPPP1PPP/RNB1KBNR b KQkq - 1 2', ['e4', 'f5', 'Qh5+'], {
        student_color: 'black',
      }),
    );
    expect(view?.in_check).toBe(true);
    expect(view?.student_to_move).toBe(true);
  });

  it('is not in check on a quiet position or an unreadable FEN', () => {
    expect(gameViewFromBoard(liveBoard('rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2', ['e4', 'e5']))?.in_check).toBe(false);
    expect(gameViewFromBoard(liveBoard('not a fen', []))?.in_check).toBe(false);
  });
});
