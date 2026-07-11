/**
 * @vitest-environment jsdom
 *
 * BotAvatar shows the avatar image when present, and gracefully falls back to
 * the bot emoji (on a tinted circle) both when no avatar is set and when the
 * image 404s at runtime.
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render, fireEvent } from '@testing-library/react';

vi.mock('next/font/google', () => ({
  Fredoka: () => ({ style: { fontFamily: 'Fredoka' }, variable: 'fredoka', className: 'fredoka' }),
  Nunito: () => ({ style: { fontFamily: 'Nunito' }, variable: 'nunito', className: 'nunito' }),
}));

import BotAvatar from '../BotAvatar';
import type { Bot } from '@/data/bots';

const bot: Bot = {
  id: 'viktor-1700',
  name: 'Viktor',
  rating: 1700,
  tier: 'advanced',
  description: 'Aggressive attacker',
  playStyle: 'Aggressive',
  avatar: '/bots/viktor.webp',
  emoji: '🔥',
};

const noAvatar: Bot = { ...bot, avatar: undefined };

afterEach(cleanup);

describe('BotAvatar', () => {
  it('renders the avatar image when the bot has one', () => {
    const { container } = render(
      <BotAvatar bot={bot} size={84} tint="#FFF3E9" deep="#C2410C" />,
    );
    const img = container.querySelector('img');
    expect(img?.getAttribute('src')).toBe('/bots/viktor.webp');
    expect(container.querySelector('[data-testid="bot-avatar-fallback"]')).toBeNull();
  });

  it('falls back to the emoji when the image fails to load (404)', () => {
    const { container } = render(
      <BotAvatar bot={bot} size={84} tint="#FFF3E9" deep="#C2410C" />,
    );
    const img = container.querySelector('img') as HTMLImageElement;
    fireEvent.error(img);
    expect(container.querySelector('img')).toBeNull();
    const fallback = container.querySelector('[data-testid="bot-avatar-fallback"]');
    expect(fallback?.textContent).toBe('🔥');
  });

  it('shows the emoji fallback immediately when no avatar is set', () => {
    const { container } = render(
      <BotAvatar bot={noAvatar} size={84} tint="#FFF3E9" deep="#C2410C" />,
    );
    expect(container.querySelector('img')).toBeNull();
    expect(container.querySelector('[data-testid="bot-avatar-fallback"]')?.textContent).toBe('🔥');
  });
});
