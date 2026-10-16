// @vitest-environment jsdom
//
// Auto-save wiring of the Database editor: treeAutoSaveEntry decides what is
// saved, createTreeSaver writes it, useAutoSave schedules it.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useState } from 'react';
import { createTreeSaver, treeAutoSaveEntry, type TreeSaveOutcome } from '../saveGameTree';
import { useAutoSave } from '../useAutoSave';
import type { OpenedGame } from '../GameViewerPanel';
import type { UserGame } from '@/hooks/useUserGames';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

const draft: OpenedGame = {
  id: 'new-variation-1', white: '?', black: '?', result: '*', pgn: '',
  moves: [], fens: [], startingFen: START, source: 'user', isDraft: true,
};
const own: OpenedGame = { ...draft, id: 'game-7', isDraft: undefined, pgn: '1. e4 *' };

interface Edit {
  game: OpenedGame;
  pgn: string;
  hasMoves: boolean;
  isDirty: boolean;
}

function setup(game: OpenedGame) {
  let resolveCreate!: (g: UserGame | null) => void;
  const createGame = vi.fn(() => new Promise<UserGame | null>(r => { resolveCreate = r; }));
  const updateGame = vi.fn().mockResolvedValue({ id: 'updated' });
  const outcomes: TreeSaveOutcome[] = [];
  const hook = renderHook((edit: Edit) => {
    const [save] = useState(() => createTreeSaver(
      () => ({ databaseId: 'db-1', createGame, updateGame }),
      o => outcomes.push(o),
    ));
    return useAutoSave({
      scope: 'tab',
      entry: treeAutoSaveEntry(edit.game, edit.pgn, edit),
      save,
      delayMs: edit.game.isDraft ? 0 : 1500,
    });
  }, { initialProps: { game, pgn: '*', hasMoves: false, isDirty: false } });
  return { ...hook, createGame, updateGame, outcomes, resolveCreate: (g: UserGame | null) => resolveCreate(g) };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('auto-save — variation draft', () => {
  it('creates exactly one game for three quick moves, then updates it', async () => {
    const s = setup(draft);
    s.rerender({ game: draft, pgn: '1. e4 *', hasMoves: true, isDirty: true });
    await act(() => vi.advanceTimersByTimeAsync(0));
    s.rerender({ game: draft, pgn: '1. e4 e5 *', hasMoves: true, isDirty: true });
    await act(() => vi.advanceTimersByTimeAsync(0));
    s.rerender({ game: draft, pgn: '1. e4 e5 2. Nf3 *', hasMoves: true, isDirty: true });
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(s.createGame).toHaveBeenCalledTimes(1);
    expect(s.createGame).toHaveBeenCalledWith('1. e4 *', expect.objectContaining({ event: 'Variation', database_id: 'db-1' }));

    await act(async () => { s.resolveCreate({ id: 'created-1' } as UserGame); });
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(s.createGame).toHaveBeenCalledTimes(1);
    expect(s.outcomes[0]).toEqual({ oldId: 'new-variation-1', newId: 'created-1', pgn: '1. e4 *' });
    expect(s.updateGame).toHaveBeenLastCalledWith('created-1', { pgn: '1. e4 e5 2. Nf3 *' });
    expect(s.outcomes.slice(1).every(o => o.oldId === 'created-1' && o.newId === 'created-1')).toBe(true);
  });

  it('creates a title-only draft', async () => {
    const s = setup(draft);
    const titled = { ...draft, title: 'Najdorf idea' };
    s.rerender({ game: titled, pgn: '*', hasMoves: false, isDirty: false });
    await act(() => vi.advanceTimersByTimeAsync(0));
    expect(s.createGame).toHaveBeenCalledTimes(1);
    expect(s.createGame).toHaveBeenCalledWith('*', expect.objectContaining({ title: 'Najdorf idea' }));
  });

  it('never creates an empty draft', async () => {
    const s = setup(draft);
    s.rerender({ game: draft, pgn: '*', hasMoves: false, isDirty: true });
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(s.createGame).not.toHaveBeenCalled();
    expect(s.result.current.hasUnsaved()).toBe(false);
  });
});

describe('auto-save — own and read-only games', () => {
  it('auto-saves an edit of an own game via updateGame({ pgn })', async () => {
    const s = setup(own);
    s.rerender({ game: own, pgn: '1. e4 c5 *', hasMoves: true, isDirty: true });
    await act(() => vi.advanceTimersByTimeAsync(1500));
    expect(s.updateGame).toHaveBeenCalledTimes(1);
    expect(s.updateGame).toHaveBeenCalledWith('game-7', { pgn: '1. e4 c5 *' });
    expect(s.createGame).not.toHaveBeenCalled();
  });

  // Master games keep their DB source; shared games arrive without user_id, so
  // they keep their stored source (e.g. board_entry) instead of 'user'.
  it.each(['twic', 'lichess', 'board_entry'])('never saves a %s game', async (source) => {
    const readOnly = { ...own, source } as OpenedGame;
    const s = setup(readOnly);
    s.rerender({ game: readOnly, pgn: '1. e4 c5 *', hasMoves: true, isDirty: true });
    await act(() => vi.advanceTimersByTimeAsync(5000));
    expect(s.updateGame).not.toHaveBeenCalled();
    expect(s.createGame).not.toHaveBeenCalled();
  });
});
