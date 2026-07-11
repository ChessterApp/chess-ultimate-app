/**
 * @vitest-environment jsdom
 *
 * BotCard renders an avatar image when the bot has an `avatar`, and falls back
 * to the name initial when it does not. Description/playStyle come from the
 * `bots` translations (mocked here to echo the key, so we assert lookups happen).
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

// Echo the key so we can prove the component reaches for a translation, and
// report every key as "missing" so the raw bots.ts fallback is exercised too.
vi.mock('next-intl', () => ({
  useTranslations: () => {
    const t = (key: string) => `bots.${key}`;
    t.has = () => false;
    return t;
  },
}));

// next/font/google is compiled by Next's SWC plugin and can't run under Vitest,
// so stub the font loaders to return the shape the component reads (`style.fontFamily`).
vi.mock('next/font/google', () => ({
  Fredoka: () => ({ style: { fontFamily: 'Fredoka' }, variable: 'fredoka', className: 'fredoka' }),
  Nunito: () => ({ style: { fontFamily: 'Nunito' }, variable: 'nunito', className: 'nunito' }),
}));

import BotCard from '../BotCard';
import type { Bot } from '@/data/bots';

const withAvatar: Bot = {
  id: 'luna-1100',
  name: 'Luna',
  rating: 1100,
  tier: 'beginner',
  description: 'Friendly and encouraging, perfect for your first games',
  playStyle: 'Patient',
  avatar: '/bots/luna.webp',
  emoji: '🌙',
  colors: { main: '#38BDF8', deep: '#0369A1', tint: '#EAF7FF' },
};

const noAvatar: Bot = {
  id: 'sven-1400',
  name: 'Sven',
  rating: 1400,
  tier: 'intermediate',
  description: 'Strategic thinker with solid fundamentals',
  playStyle: 'Strategic',
};

afterEach(cleanup);

describe('BotCard', () => {
  it('renders the avatar image when bot.avatar is set', () => {
    const { container } = render(<BotCard bot={withAvatar} onClick={() => {}} />);
    const img = container.querySelector('img');
    expect(img).not.toBeNull();
    expect(img?.getAttribute('src')).toBe('/bots/luna.webp');
    expect(img?.getAttribute('alt')).toBe('Luna');
  });

  it('falls back to the name initial when bot.avatar is missing', () => {
    const { container } = render(<BotCard bot={noAvatar} onClick={() => {}} />);
    expect(container.querySelector('img')).toBeNull();
    expect(container.textContent).toContain('S');
  });

  it('keeps the bot name visible', () => {
    const { container } = render(<BotCard bot={withAvatar} onClick={() => {}} />);
    expect(container.textContent).toContain('Luna');
  });

  it('shows description and play style (falling back to raw strings)', () => {
    const { container } = render(<BotCard bot={withAvatar} onClick={() => {}} />);
    expect(container.textContent).toContain(
      'Friendly and encouraging, perfect for your first games',
    );
    expect(container.textContent).toContain('Patient');
  });

  it('shows the rating pill and play-style emoji', () => {
    const { container } = render(<BotCard bot={withAvatar} onClick={() => {}} />);
    expect(container.textContent).toContain('1100');
    expect(container.textContent).toContain('🌙');
  });

  it('is keyboard-focusable and exposes selected state', () => {
    const { container } = render(
      <BotCard bot={withAvatar} selected onClick={() => {}} />,
    );
    const card = container.querySelector('[role="button"]');
    expect(card).not.toBeNull();
    expect(card?.getAttribute('tabindex')).toBe('0');
    expect(card?.getAttribute('aria-pressed')).toBe('true');
  });
});
