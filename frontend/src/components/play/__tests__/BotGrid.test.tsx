/**
 * @vitest-environment jsdom
 *
 * BotGrid renders one "world" section per tier: a world banner (emoji + world
 * name + tier sub-label) followed by the tier's cards. The translator mock
 * echoes keys so we can assert the world/tier lookups happen, and reports every
 * key as missing so raw fallbacks are exercised too.
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

import BotGrid from '../BotGrid';
import { TIER_WORLDS, TIER_LABELS } from '@/data/bots';

afterEach(cleanup);

describe('BotGrid world sections', () => {
  it('renders a world banner (emoji + name + tier) for every tier', () => {
    const { container } = render(<BotGrid selectedBotId={null} onSelectBot={() => {}} />);
    const text = container.textContent ?? '';

    for (const world of Object.values(TIER_WORLDS)) {
      expect(text).toContain(world.emoji);
      // worldName falls back to the raw key when the translation is missing.
      expect(text).toContain(`worlds.${world.key}`);
    }

    // Tier sub-labels (tierLabel falls back to the hardcoded TIER_LABELS).
    for (const label of Object.values(TIER_LABELS)) {
      expect(text).toContain(label);
    }
  });

  it('paints each tier world scenery on its cards', () => {
    const { container } = render(<BotGrid selectedBotId={null} onSelectBot={() => {}} />);
    const tiers = Array.from(
      container.querySelectorAll('[data-testid="world-scenery"]'),
    ).map((el) => el.getAttribute('data-tier'));

    for (const tier of Object.keys(TIER_WORLDS)) {
      expect(tiers).toContain(tier);
    }
  });

  it('renders real beginner avatars and placeholders for tiers without art', () => {
    const { container } = render(<BotGrid selectedBotId={null} onSelectBot={() => {}} />);
    // Beginner heroes have real avatar images.
    expect(container.querySelectorAll('img').length).toBeGreaterThan(0);
    // Non-beginner tiers show the "Art coming soon" placeholder.
    expect(
      container.querySelectorAll('[data-testid="bot-placeholder"]').length,
    ).toBeGreaterThan(0);
  });
});
