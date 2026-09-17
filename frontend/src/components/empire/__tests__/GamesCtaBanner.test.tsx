/**
 * @vitest-environment jsdom
 *
 * Tests for the Empire games CTA banner:
 *   - renders the localized title / subtitle / button copy
 *   - the whole card links to /games
 *   - carries the expected data-testids
 */
import { describe, it, expect, afterEach, vi } from 'vitest';
import { cleanup, render } from '@testing-library/react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

import GamesCtaBanner from '../GamesCtaBanner';

afterEach(() => {
  cleanup();
});

describe('GamesCtaBanner', () => {
  it('renders the title, subtitle, and button copy', () => {
    const { getByTestId } = render(<GamesCtaBanner />);
    const root = getByTestId('empire-games-cta');
    expect(root.textContent).toContain('gamesCtaTitle');
    expect(root.textContent).toContain('gamesCtaSubtitle');
    expect(getByTestId('empire-games-cta-button').textContent).toContain(
      'gamesCtaButton',
    );
  });

  it('links the whole card to /games', () => {
    const { getByTestId } = render(<GamesCtaBanner />);
    const root = getByTestId('empire-games-cta');
    expect(root.tagName).toBe('A');
    expect(root.getAttribute('href')).toBe('/games');
  });

  it('passes through a className', () => {
    const { getByTestId } = render(<GamesCtaBanner className="mt-4" />);
    expect(getByTestId('empire-games-cta').className).toContain('mt-4');
  });
});
