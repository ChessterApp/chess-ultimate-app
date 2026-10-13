/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { cleanup, render } from '@testing-library/react';

vi.mock('next-intl', () => ({ useTranslations: () => (k: string) => k }));
vi.mock('../TugBoard', () => ({ default: () => null }));
vi.mock('../RopeScene', () => ({ default: () => null }));
vi.mock('@/lib/tug-of-war/sound', () => ({
  TugSound: class {
    win() {}
    setMuted() {}
    dispose() {}
  },
  loadMuted: () => true,
  saveMuted: () => {},
}));
vi.mock('@/lib/tug-of-war/confetti', () => ({
  fireWinConfetti: async () => {},
  resetConfetti: async () => {},
}));
const trackMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics/events', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics/events')>()),
  track: trackMock,
}));

import MatchScreen from '../MatchScreen';
import { initialState, type GameState } from '@/lib/tug-of-war/gameReducer';

afterEach(() => {
  cleanup();
  trackMock.mockReset();
});

describe('MatchScreen — tug_of_war_finished', () => {
  it('fires once on match → over with the winning side only (no team names)', () => {
    const match: GameState = { ...initialState('Masha', 'Petya'), phase: 'match' };
    const { rerender } = render(<MatchScreen state={match} dispatch={vi.fn()} />);
    expect(trackMock).not.toHaveBeenCalled();

    const over: GameState = { ...match, phase: 'over', winner: 'B' };
    rerender(<MatchScreen state={over} dispatch={vi.fn()} />);
    rerender(<MatchScreen state={{ ...over }} dispatch={vi.fn()} />);

    expect(trackMock).toHaveBeenCalledTimes(1);
    expect(trackMock).toHaveBeenCalledWith('tug_of_war_finished', { winner_side: 'B' });
    expect(JSON.stringify(trackMock.mock.calls)).not.toMatch(/Masha|Petya/);
  });
});
