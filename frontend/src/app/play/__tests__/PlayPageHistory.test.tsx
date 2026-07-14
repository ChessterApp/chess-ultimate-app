/**
 * @vitest-environment jsdom
 *
 * PlayPage back-navigation: phase transitions are mirrored to the URL, and a
 * popstate out of `playing` cancels the pending bot move so no stale move fires.
 * Child components and engines are stubbed so the test targets PlayPage's own
 * state/URL/cancellation logic.
 */
import { describe, it, expect, beforeEach, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent, act } from '@testing-library/react';

const { evaluatePositionMock, getMoveMock } = vi.hoisted(() => ({
  evaluatePositionMock: vi.fn(),
  getMoveMock: vi.fn(),
}));

vi.mock('next/font/google', () => ({
  Fredoka: () => ({ style: { fontFamily: 'Fredoka' }, variable: 'fredoka', className: 'fredoka' }),
  Nunito: () => ({ style: { fontFamily: 'Nunito' }, variable: 'nunito', className: 'nunito' }),
}));

vi.mock('next-intl', () => ({
  useTranslations: () => {
    const t = (k: string) => k;
    (t as any).has = () => false;
    return t;
  },
}));

vi.mock('@/lib/analytics/events', () => ({
  ANALYTICS_EVENTS: { PLAY_ENGINE_WAIT: 'play_engine_wait' },
  track: vi.fn(),
}));

vi.mock('@/hooks/useMaia', () => ({
  useMaia: () => ({
    status: 'ready',
    error: null,
    evaluatePosition: evaluatePositionMock,
    downloadModel: vi.fn(),
    usingServerFallback: false,
  }),
}));

vi.mock('@/hooks/useStockfishPlay', () => ({
  useStockfishPlay: () => ({ status: 'ready', error: null, getMove: getMoveMock }),
}));

vi.mock('@/components/play/BotGrid', async () => {
  const actual: any = await vi.importActual('@/data/bots');
  const bot = actual.getBotById('luna-1100');
  return {
    default: ({ onSelectBot }: any) =>
      React.createElement(
        'button',
        { 'data-testid': 'pick-bot', onClick: () => onSelectBot(bot) },
        'pick',
      ),
  };
});

vi.mock('@/components/play/GameSetup', () => ({
  default: ({ onPlay, onColorChange, onChangeBot }: any) =>
    React.createElement('div', { 'data-testid': 'setup-screen' }, [
      React.createElement('button', { key: 'p', 'data-testid': 'play', onClick: onPlay }, 'play'),
      React.createElement(
        'button',
        { key: 'b', 'data-testid': 'color-black', onClick: () => onColorChange('black') },
        'black',
      ),
      React.createElement(
        'button',
        { key: 'c', 'data-testid': 'change-bot', onClick: onChangeBot },
        'change',
      ),
    ]),
}));

vi.mock('@/components/play/GameHeader', () => ({ default: () => null }));

vi.mock('@/components/play/GameDock', () => ({
  default: ({ onNewGame, onResign }: any) =>
    React.createElement('div', null, [
      React.createElement('button', { key: 'n', 'data-testid': 'new-game', onClick: onNewGame }, 'new'),
      React.createElement('button', { key: 'r', 'data-testid': 'resign', onClick: onResign }, 'resign'),
    ]),
}));

vi.mock('@/components/chess/ChessgroundBoard', () => ({
  default: ({ onMove }: any) =>
    React.createElement(
      'button',
      { 'data-testid': 'board-move', onClick: () => onMove('e2', 'e4') },
      'move',
    ),
}));

import PlayPage from '../page';

describe('PlayPage URL history sync', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/play');
    evaluatePositionMock.mockReset().mockResolvedValue({ policy: { e2e4: 1 } });
    getMoveMock.mockReset().mockResolvedValue('e2e4');
  });

  afterEach(() => {
    cleanup();
    vi.useRealTimers();
  });

  it('mirrors phase transitions to the URL query string', () => {
    const { getByTestId } = render(<PlayPage />);
    expect(window.location.search).toBe('');

    fireEvent.click(getByTestId('pick-bot'));
    expect(window.location.search).toBe('?phase=setup&bot=luna-1100');

    fireEvent.click(getByTestId('play'));
    expect(window.location.search).toBe('?phase=playing&bot=luna-1100');
  });

  it('restores setup and cancels the pending bot move on popstate out of playing', async () => {
    vi.useFakeTimers();
    const { getByTestId } = render(<PlayPage />);

    act(() => { fireEvent.click(getByTestId('pick-bot')); });
    act(() => { fireEvent.click(getByTestId('color-black')); });
    // Play as black → bot is scheduled to move first (500ms delay).
    act(() => { fireEvent.click(getByTestId('play')); });
    expect(window.location.search).toBe('?phase=playing&bot=luna-1100');

    // Browser Back to the setup entry before the bot's timer fires.
    act(() => {
      window.history.replaceState(null, '', '/play?phase=setup&bot=luna-1100');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    // Flush the (now cancelled) 500ms bot-move timer.
    await act(async () => { vi.advanceTimersByTime(1000); });

    expect(evaluatePositionMock).not.toHaveBeenCalled();
    expect(getByTestId('setup-screen')).toBeTruthy();
    expect(window.location.search).toBe('?phase=setup&bot=luna-1100');
  });

  it('fires the bot move when the game is NOT interrupted (control)', async () => {
    vi.useFakeTimers();
    const { getByTestId } = render(<PlayPage />);

    act(() => { fireEvent.click(getByTestId('pick-bot')); });
    act(() => { fireEvent.click(getByTestId('color-black')); });
    act(() => { fireEvent.click(getByTestId('play')); });

    await act(async () => { vi.advanceTimersByTime(1000); });

    expect(evaluatePositionMock).toHaveBeenCalled();
  });
});
