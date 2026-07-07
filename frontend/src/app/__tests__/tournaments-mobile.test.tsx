// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen } from '@testing-library/react';
import React from 'react';

vi.mock('next/link', () => ({
  __esModule: true,
  default: ({ children, href }: { children: React.ReactNode; href: string }) => (
    <a href={href}>{children}</a>
  ),
}));

import TournamentsPage from '../tournaments/page';

function setWidth(w: number) {
  Object.defineProperty(window, 'innerWidth', { value: w, writable: true, configurable: true });
}

describe('Tournaments responsive view', () => {
  beforeEach(() => {
    // fetch is called on mount; stub it so the effect resolves cleanly.
    global.fetch = vi.fn(() =>
      Promise.resolve({ ok: true, json: () => Promise.resolve({ tournaments: [] }) })
    ) as unknown as typeof fetch;
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  it('hides the calendar toggle and shows the list on small screens', () => {
    setWidth(375);
    render(<TournamentsPage />);
    expect(screen.queryByRole('button', { name: /^calendar$/i })).toBeNull();
    // List view renders its status filter select
    expect(screen.getByRole('combobox')).toBeTruthy();
  });

  it('shows the calendar/list toggle on desktop', () => {
    setWidth(1280);
    render(<TournamentsPage />);
    expect(screen.getByRole('button', { name: /^calendar$/i })).toBeTruthy();
    expect(screen.getByRole('button', { name: /^list$/i })).toBeTruthy();
  });
});
