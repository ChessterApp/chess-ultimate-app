/**
 * @vitest-environment jsdom
 *
 * GameSidebar carries the bot's tier "world" theme into the in-game panel:
 * world emoji + name, an emoji-fallback avatar, a themed thinking bubble, a
 * world-colored game-over panel, and a New Game control.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent } from '@testing-library/react';

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

import GameSidebar from '../GameSidebar';
import type { Bot, BotTier } from '@/data/bots';
import { TIER_WORLDS } from '@/data/bots';

const makeBot = (tier: BotTier, avatar?: string): Bot => ({
  id: `test-${tier}`,
  name: 'Testy',
  rating: 1500,
  tier,
  description: `A ${tier} test bot`,
  playStyle: 'Solid',
  avatar,
  emoji: '🤖',
});

const TIERS: BotTier[] = ['beginner', 'intermediate', 'advanced', 'master'];

const baseProps = {
  playerColor: 'w' as const,
  thinking: false,
  gameResult: null,
  onNewGame: () => {},
};

afterEach(cleanup);

describe('GameSidebar world theming', () => {
  it.each(TIERS)('renders the %s world theme', (tier) => {
    const world = TIER_WORLDS[tier];
    const { container, getByTestId } = render(
      <GameSidebar {...baseProps} bot={makeBot(tier, '/bots/test.webp')} />,
    );
    expect(getByTestId('game-sidebar').getAttribute('data-tier')).toBe(tier);
    // Tier-specific world emoji watermark proves the theme is wired in.
    expect(container.textContent ?? '').toContain(world.emoji);
  });
});

describe('GameSidebar avatar', () => {
  it('renders the avatar image when present', () => {
    const { container } = render(
      <GameSidebar {...baseProps} bot={makeBot('advanced', '/bots/test.webp')} />,
    );
    // Both desktop banner and mobile bar render an avatar image.
    expect(container.querySelector('img')?.getAttribute('src')).toBe('/bots/test.webp');
  });

  it('falls back to the emoji avatar when no image is set', () => {
    const { container } = render(
      <GameSidebar {...baseProps} bot={makeBot('advanced')} />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('[data-testid="bot-avatar-fallback"]')?.textContent).toBe('🤖');
  });
});

describe('GameSidebar thinking state', () => {
  it('shows a themed thinking bubble only while thinking', () => {
    const idle = render(<GameSidebar {...baseProps} bot={makeBot('beginner', '/bots/test.webp')} />);
    expect(idle.container.querySelector('[data-testid="thinking-bubble"]')).toBeNull();
    cleanup();

    const busy = render(
      <GameSidebar {...baseProps} thinking bot={makeBot('beginner', '/bots/test.webp')} />,
    );
    const bubble = busy.container.querySelector('[data-testid="thinking-bubble"]');
    expect(bubble).not.toBeNull();
    expect(bubble?.textContent).toContain('is thinking');
  });
});

describe('GameSidebar game-over state', () => {
  it('shows the game-over panel with the result text when the game ends', () => {
    const { container } = render(
      <GameSidebar
        {...baseProps}
        gameResult="White wins by checkmate!"
        bot={makeBot('master', '/bots/test.webp')}
      />,
    );
    const panel = container.querySelector('[data-testid="game-over-panel"]');
    expect(panel).not.toBeNull();
    expect(panel?.textContent).toContain('White wins by checkmate!');
  });

  it('hides the game-over panel during play', () => {
    const { container } = render(
      <GameSidebar {...baseProps} bot={makeBot('master', '/bots/test.webp')} />,
    );
    expect(container.querySelector('[data-testid="game-over-panel"]')).toBeNull();
  });
});

describe('GameSidebar interactions', () => {
  it('fires onNewGame when the New Game button is clicked', () => {
    const onNewGame = vi.fn();
    const { getByText } = render(
      <GameSidebar {...baseProps} onNewGame={onNewGame} bot={makeBot('beginner', '/bots/test.webp')} />,
    );
    fireEvent.click(getByText(/New game/));
    expect(onNewGame).toHaveBeenCalled();
  });
});
