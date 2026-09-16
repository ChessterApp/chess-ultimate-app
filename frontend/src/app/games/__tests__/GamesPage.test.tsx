// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import GamesPage from '../page';

// next-intl — echo keys so assertions are locale-independent.
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => `[${key}]`,
}));

// next/image — passthrough to a plain img.
vi.mock('next/image', () => ({
  __esModule: true,
  default: (props: Record<string, unknown>) => {
    const { fill: _fill, priority: _priority, sizes: _sizes, ...rest } = props as {
      fill?: boolean;
      priority?: boolean;
      sizes?: string;
    } & Record<string, unknown>;
    // eslint-disable-next-line @next/next/no-img-element
    return <img {...(rest as { alt?: string })} alt={(rest.alt as string) || ''} />;
  },
}));

afterEach(cleanup);

describe('GamesPage', () => {
  it('renders both game cards linking to the game routes', () => {
    render(<GamesPage />);
    const wheel = screen.getByRole('link', { name: '[wheel.title]' });
    const tug = screen.getByRole('link', { name: '[tugOfWar.title]' });
    expect(wheel.getAttribute('href')).toBe('/games/wheel');
    expect(tug.getAttribute('href')).toBe('/games/tug-of-war');
  });

  it('renders poster images for both games', () => {
    const { container } = render(<GamesPage />);
    const srcs = Array.from(container.querySelectorAll('img')).map((img) =>
      img.getAttribute('src'),
    );
    expect(srcs).toContain('/games/wheel-poster.webp');
    expect(srcs).toContain('/games/tug-of-war-poster.webp');
  });

  it('renders titles and descriptions for both games', () => {
    render(<GamesPage />);
    expect(screen.getByText('[wheel.description]')).toBeTruthy();
    expect(screen.getByText('[tugOfWar.description]')).toBeTruthy();
    expect(screen.getByText('[title]')).toBeTruthy();
  });
});
