/**
 * @vitest-environment jsdom
 *
 * GameHeader is the V3 "Immersive World" bot header: rounded-square avatar,
 * white bot name, gold rating pill + translucent world pill, and a themed
 * "thinking…" speech bubble (always mounted; visible only while thinking).
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

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

import GameHeader from '../GameHeader';
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

afterEach(cleanup);

describe('GameHeader', () => {
  it.each(TIERS)('renders the %s world emoji, name and rating', (tier) => {
    const world = TIER_WORLDS[tier];
    const { container, getByTestId } = render(
      <GameHeader bot={makeBot(tier, '/bots/test.webp')} thinking={false} />,
    );
    expect(getByTestId('game-header').getAttribute('data-tier')).toBe(tier);
    const text = container.textContent ?? '';
    expect(text).toContain('Testy');
    expect(text).toContain('1500');
    expect(text).toContain(world.emoji);
  });

  it('keeps the thinking bubble mounted in both states so the header never changes height', () => {
    // Regression: a conditionally-mounted bubble grew/shrank the header on
    // every bot move, pushing the board down and back up ("board wobble").
    const idle = render(<GameHeader bot={makeBot('beginner', '/bots/test.webp')} thinking={false} />);
    const idleBubble = idle.container.querySelector<HTMLElement>('[data-testid="thinking-bubble"]');
    expect(idleBubble).not.toBeNull();
    expect(idleBubble?.getAttribute('data-thinking')).toBe('false');
    // Hidden via visibility (space stays reserved), never unmounted or display:none.
    expect(getComputedStyle(idleBubble!).visibility).toBe('hidden');
    expect(getComputedStyle(idleBubble!).display).not.toBe('none');
    cleanup();

    const busy = render(<GameHeader bot={makeBot('beginner', '/bots/test.webp')} thinking />);
    const bubble = busy.container.querySelector<HTMLElement>('[data-testid="thinking-bubble"]');
    expect(bubble).not.toBeNull();
    expect(bubble?.getAttribute('data-thinking')).toBe('true');
    expect(getComputedStyle(bubble!).visibility).toBe('visible');
    expect(bubble?.textContent).toContain('is thinking');
  });

  it('shows the syncing pill only when syncing', () => {
    const off = render(<GameHeader bot={makeBot('advanced', '/bots/test.webp')} thinking={false} />);
    expect(off.container.querySelector('[data-testid="syncing-pill"]')).toBeNull();
    cleanup();

    const on = render(<GameHeader bot={makeBot('advanced', '/bots/test.webp')} thinking={false} syncing />);
    expect(on.container.querySelector('[data-testid="syncing-pill"]')).not.toBeNull();
  });
});
