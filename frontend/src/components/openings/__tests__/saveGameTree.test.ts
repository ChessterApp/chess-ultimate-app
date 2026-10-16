import { describe, it, expect, vi } from 'vitest';
import { saveGameTree } from '../saveGameTree';
import type { OpenedGame } from '../GameViewerPanel';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

const draft: OpenedGame = {
  id: 'new-variation-1', white: '?', black: '?', result: '*', pgn: '',
  moves: [], fens: [], startingFen: START, source: 'user', isDraft: true,
};

const saved: OpenedGame = { ...draft, id: 'game-7', isDraft: undefined, pgn: '1. e4' };

function deps(databaseId: string | null) {
  return {
    databaseId,
    createGame: vi.fn().mockResolvedValue({ id: 'created-1' }),
    updateGame: vi.fn().mockResolvedValue({ id: 'game-7' }),
  };
}

describe('saveGameTree', () => {
  it('creates a new game for a draft, filed under the active database', async () => {
    const d = deps('db-1');
    const result = await saveGameTree(draft, '1. e4 {idea} 1... e5', d);
    expect(result).toEqual({ id: 'created-1' });
    expect(d.updateGame).not.toHaveBeenCalled();
    expect(d.createGame).toHaveBeenCalledWith('1. e4 {idea} 1... e5', expect.objectContaining({
      white: '?', black: '?', result: '*', event: 'Variation', database_id: 'db-1',
    }));
  });

  it('omits database_id for a draft when no database is selected', async () => {
    const d = deps(null);
    await saveGameTree(draft, '1. d4', d);
    expect(d.createGame.mock.calls[0][1].database_id).toBeUndefined();
  });

  it('updates an already-saved game in place', async () => {
    const d = deps('db-1');
    await saveGameTree(saved, '1. e4 e5', d);
    expect(d.createGame).not.toHaveBeenCalled();
    expect(d.updateGame).toHaveBeenCalledWith('game-7', { pgn: '1. e4 e5' });
  });
});
