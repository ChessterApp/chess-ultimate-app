// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { act, renderHook } from '@testing-library/react';
import { gameReducer, initialState, type GameAction, type GameState } from '../gameReducer';
import { useAdaptiveBot, type AdaptiveSession } from '../useAdaptiveBot';
import { CREEP_EVERY_MS, type SavedAdaptive } from '../adaptive';
import type { TugPuzzle } from '../types';

const puzzle = (id: string, rating = 900): TugPuzzle => ({ id, fen: '8/8/8/8/8/8/8/8 w - - 0 1', moves: ['a1a2'], rating, themes: [] });

const started = (): GameState =>
  gameReducer(initialState(), {
    type: 'START_MATCH',
    teamAName: 'You',
    teamBName: 'Chesster',
    queueA: [puzzle('a1'), puzzle('a2'), puzzle('a3')],
    queueB: [puzzle('b1'), puzzle('b2')],
  });

describe('useAdaptiveBot', () => {
  let clockMs = 0;
  beforeEach(() => {
    vi.useFakeTimers();
    clockMs = 0;
  });
  afterEach(() => vi.useRealTimers());

  const setup = (saved: SavedAdaptive | null = null) => {
    const save = vi.fn();
    const session: AdaptiveSession = { saved };
    let game = started();
    const hook = renderHook(
      (props: { game: GameState }) =>
        useAdaptiveBot(session, props.game, { clock: () => clockMs, now: () => new Date(0), save }),
      { initialProps: { game } },
    );
    const send = (action: GameAction) => {
      game = gameReducer(game, action);
      hook.rerender({ game });
    };
    return { ...hook, send, save };
  };

  it('is idle without a session', () => {
    const { result } = renderHook(() => useAdaptiveBot(null, started()));
    expect(result.current).toBeNull();
  });

  it('starts from the saved estimate', () => {
    const { result } = setup({ estimate: 1340, avgSeconds: 7, peakBotLevel: null, date: '' });
    expect(result.current!.state.player.estimate).toBe(1340);
    expect(result.current!.bot.rating).toBe(1040);
  });

  it('a human solve scores the player with the solve time and steps the bot up', () => {
    const { result, send } = setup();
    clockMs = 6000;
    send({ type: 'SOLVE', team: 'A' });
    const s = result.current!.state;
    expect(s.player.estimate).toBeGreaterThan(1000);
    expect(s.player.avgSeconds).toBe(6);
    expect(s.ladder.rating).toBe(800);
    expect(result.current!.bot.secondsPerMove).toBe(13);
  });

  it('a bot solve drops it; three wrongs (a skip) lower the estimate', () => {
    const { result, send } = setup();
    send({ type: 'SOLVE', team: 'B' });
    expect(result.current!.state.ladder.rating).toBe(650);
    for (let i = 0; i < 3; i++) send({ type: 'WRONG', team: 'A' });
    expect(result.current!.state.player.estimate).toBeLessThan(1000);
  });

  it('creeps every 20 s while the match is live', () => {
    const { result } = setup();
    act(() => vi.advanceTimersByTime(CREEP_EVERY_MS * 2));
    expect(result.current!.state.ladder.rating).toBe(750);
  });

  it('persists the result once when the match ends, including the final solve', () => {
    const { result, send, save } = setup();
    send({ type: 'SOLVE', team: 'A' });
    send({ type: 'TIME_UP' });
    expect(save).toHaveBeenCalledTimes(1);
    expect(result.current!.result).toEqual(save.mock.calls[0][0]);
    expect(result.current!.result!.peakBotLevel).toBe('junior');
    act(() => vi.advanceTimersByTime(CREEP_EVERY_MS * 3));
    expect(result.current!.state.ladder.rating).toBe(800); // no creep after the end
    expect(save).toHaveBeenCalledTimes(1);
  });
});
