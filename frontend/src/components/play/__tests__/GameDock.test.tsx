/**
 * @vitest-environment jsdom
 *
 * GameDock is the V3 "Immersive World" bottom dock: the player line plus two
 * pill actions (Resign — gated behind a confirm dialog — and New game). There
 * is intentionally no Hint button.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent, waitFor } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => {
    const t = (key: string) => `bots.${key}`;
    t.has = () => false;
    return t;
  },
}));

vi.mock('next/font/google', () => ({
  Fredoka: () => ({ style: { fontFamily: 'Fredoka' }, variable: 'fredoka', className: 'fredoka' }),
  Nunito: () => ({ style: { fontFamily: 'Nunito' }, variable: 'nunito', className: 'nunito' }),
}));

import GameDock from '../GameDock';
import type { Bot, BotTier } from '@/data/bots';

const makeBot = (tier: BotTier = 'beginner'): Bot => ({
  id: `test-${tier}`,
  name: 'Testy',
  rating: 1500,
  tier,
  description: `A ${tier} test bot`,
  playStyle: 'Solid',
  avatar: '/bots/test.webp',
  emoji: '🤖',
});

const baseProps = {
  bot: makeBot(),
  playerColor: 'w' as const,
  gameResult: null,
  onNewGame: () => {},
  onResign: () => {},
};

afterEach(cleanup);

describe('GameDock rendering', () => {
  it('renders the resign and new-game buttons while the game is in progress', () => {
    const { getByTestId } = render(<GameDock {...baseProps} />);
    expect(getByTestId('resign-button')).not.toBeNull();
    expect(getByTestId('new-game-button')).not.toBeNull();
  });

  it('has no hint button', () => {
    const { container, queryByTestId } = render(<GameDock {...baseProps} />);
    expect(queryByTestId('hint-button')).toBeNull();
    expect((container.textContent ?? '').toLowerCase()).not.toContain('hint');
  });

  it('hides the resign button and shows the result once the game has ended', () => {
    const { queryByTestId, container } = render(
      <GameDock {...baseProps} gameResult="White wins by checkmate!" />,
    );
    expect(queryByTestId('resign-button')).toBeNull();
    expect(queryByTestId('new-game-button')).not.toBeNull();
    expect(container.textContent).toContain('White wins by checkmate!');
  });
});

describe('GameDock interactions', () => {
  it('fires onNewGame when New game is clicked', () => {
    const onNewGame = vi.fn();
    const { getByTestId } = render(<GameDock {...baseProps} onNewGame={onNewGame} />);
    fireEvent.click(getByTestId('new-game-button'));
    expect(onNewGame).toHaveBeenCalledTimes(1);
  });
});

describe('GameDock resign confirm flow', () => {
  it('does not resign immediately — it opens a confirm dialog first', async () => {
    const onResign = vi.fn();
    const { getByTestId, queryByTestId } = render(<GameDock {...baseProps} onResign={onResign} />);

    // No dialog until the resign button is pressed.
    expect(queryByTestId('resign-confirm')).toBeNull();

    fireEvent.click(getByTestId('resign-button'));
    await waitFor(() => expect(getByTestId('resign-confirm')).not.toBeNull());
    // Opening the dialog must NOT end the game.
    expect(onResign).not.toHaveBeenCalled();
  });

  it('keeps the game running when the player cancels', async () => {
    const onResign = vi.fn();
    const { getByTestId, queryByTestId } = render(<GameDock {...baseProps} onResign={onResign} />);

    fireEvent.click(getByTestId('resign-button'));
    await waitFor(() => expect(getByTestId('resign-cancel')).not.toBeNull());
    fireEvent.click(getByTestId('resign-cancel'));

    expect(onResign).not.toHaveBeenCalled();
    await waitFor(() => expect(queryByTestId('resign-confirm')).toBeNull());
    // Resign button is still available — game continues.
    expect(getByTestId('resign-button')).not.toBeNull();
  });

  it('ends the game as a loss when the player confirms', async () => {
    const onResign = vi.fn();
    const { getByTestId } = render(<GameDock {...baseProps} onResign={onResign} />);

    fireEvent.click(getByTestId('resign-button'));
    await waitFor(() => expect(getByTestId('resign-confirm')).not.toBeNull());
    fireEvent.click(getByTestId('resign-confirm'));

    expect(onResign).toHaveBeenCalledTimes(1);
  });
});
