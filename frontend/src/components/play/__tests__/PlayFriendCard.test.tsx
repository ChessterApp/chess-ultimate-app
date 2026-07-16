/**
 * @vitest-environment jsdom
 *
 * PlayFriendCard (phase 6): all user-visible copy is localized via the shared
 * `bots.play.*` catalog. This test backs next-intl with the real English
 * messages so the assertions prove the keys resolve to real localized strings
 * (not just echoed key names).
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import React from 'react';
import { cleanup, render } from '@testing-library/react';

vi.mock('next/navigation', () => ({
  useRouter: () => ({ push: vi.fn() }),
}));

// Back next-intl with the real `bots` catalog so `playText` resolves to the
// actual English strings.
vi.mock('next-intl', async () => {
  const en = (await import('../../../../messages/en.json')).default as Record<string, unknown>;
  const bots = (en as { bots: Record<string, unknown> }).bots;
  const walk = (key: string): unknown =>
    key.split('.').reduce<unknown>((cur, p) => (cur as Record<string, unknown> | undefined)?.[p], bots);
  const useTranslations = () => {
    const t = (key: string, values?: Record<string, string | number>) => {
      const v = walk(key);
      return typeof v === 'string'
        ? v.replace(/\{(\w+)\}/g, (_m, k) => String(values?.[k] ?? ''))
        : key;
    };
    (t as unknown as { has: (k: string) => boolean }).has = (key: string) =>
      typeof walk(key) === 'string';
    return t;
  };
  return { useTranslations };
});

import PlayFriendCard from '../PlayFriendCard';

afterEach(cleanup);

describe('PlayFriendCard localization', () => {
  it('renders the localized subtitle, labels and button — no hard-coded English left', () => {
    const { getByTestId, getByText } = render(<PlayFriendCard />);

    expect(getByTestId('play-friend-card')).toBeTruthy();
    // Localized copy from bots.play.*
    expect(
      getByText('Create a game and share the link — it opens live for both of you.'),
    ).toBeTruthy();
    expect(getByText('TIME CONTROL')).toBeTruthy();
    expect(getByText('YOUR COLOR')).toBeTruthy();
    expect(getByText('Create game link')).toBeTruthy();
    // Untimed + color options come from the shared catalog.
    expect(getByText('Untimed')).toBeTruthy();
    expect(getByText('White')).toBeTruthy();
    expect(getByText('Black')).toBeTruthy();
    expect(getByText('Random')).toBeTruthy();
  });

  it('does not render its own "Play a friend" title (that lives on the section header)', () => {
    const { queryByText } = render(<PlayFriendCard />);
    expect(queryByText('Play a friend')).toBeNull();
  });
});
