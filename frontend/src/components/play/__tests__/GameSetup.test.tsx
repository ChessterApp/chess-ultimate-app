/**
 * @vitest-environment jsdom
 *
 * GameSetup carries the bot's tier "world" theme (banner gradient + world emoji
 * + world/tier label) into the pre-game screen, renders the overlapping avatar
 * (with emoji fallback), and wires the color picker + Play CTA.
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

import GameSetup from '../GameSetup';
import type { Bot, BotTier } from '@/data/bots';
import { TIER_WORLDS, TIER_LABELS } from '@/data/bots';

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

describe('GameSetup world theming', () => {
  it.each(TIERS)('renders the %s world theme (emoji, label, gradient)', (tier) => {
    const world = TIER_WORLDS[tier];
    const { container } = render(
      <GameSetup
        bot={makeBot(tier, '/bots/test.webp')}
        playerColor="white"
        onColorChange={() => {}}
        onPlay={() => {}}
        onChangeBot={() => {}}
      />,
    );
    const text = container.textContent ?? '';
    // Tier-specific world emoji + label prove the world theme is wired in.
    expect(text).toContain(world.emoji);
    expect(text).toContain(TIER_LABELS[tier]);
  });
});

describe('GameSetup avatar', () => {
  it('renders the overlapping avatar image when present', () => {
    const { container } = render(
      <GameSetup
        bot={makeBot('beginner', '/bots/test.webp')}
        playerColor="white"
        onColorChange={() => {}}
        onPlay={() => {}}
        onChangeBot={() => {}}
      />,
    );
    expect(container.querySelector('img')?.getAttribute('src')).toBe('/bots/test.webp');
  });

  it('falls back to the emoji avatar when no image is set', () => {
    const { container } = render(
      <GameSetup
        bot={makeBot('beginner')}
        playerColor="white"
        onColorChange={() => {}}
        onPlay={() => {}}
        onChangeBot={() => {}}
      />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('[data-testid="bot-avatar-fallback"]')?.textContent).toBe('🤖');
  });
});

describe('GameSetup interactions', () => {
  it('fires onColorChange and onPlay', () => {
    const onColorChange = vi.fn();
    const onPlay = vi.fn();
    const { getByText, getAllByRole } = render(
      <GameSetup
        bot={makeBot('beginner', '/bots/test.webp')}
        playerColor="white"
        onColorChange={onColorChange}
        onPlay={onPlay}
        onChangeBot={() => {}}
      />,
    );
    // Color picker exposes three radios.
    expect(getAllByRole('radio')).toHaveLength(3);
    fireEvent.click(getByText('Black'));
    expect(onColorChange).toHaveBeenCalledWith('black');
    fireEvent.click(getByText(/Play against Testy/));
    expect(onPlay).toHaveBeenCalled();
  });

  it('fires onChangeBot from the back control', () => {
    const onChangeBot = vi.fn();
    const { getByText } = render(
      <GameSetup
        bot={makeBot('beginner', '/bots/test.webp')}
        playerColor="white"
        onColorChange={() => {}}
        onPlay={() => {}}
        onChangeBot={onChangeBot}
      />,
    );
    fireEvent.click(getByText(/Change bot/));
    expect(onChangeBot).toHaveBeenCalled();
  });
});
