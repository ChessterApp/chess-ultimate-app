/**
 * @vitest-environment jsdom
 *
 * Companion page: the flag-off invariant (nothing companion-related renders; the
 * route 404s) and a per-locale render smoke test of the egg + competency ring.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, screen, fireEvent } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import ru from '../../../../messages/ru.json';
import kz from '../../../../messages/kz.json';

const flags = vi.hoisted(() => ({ on: true }));
vi.mock('@/lib/feature-flags', () => ({
  get COMPANION_ENABLED() {
    return flags.on;
  },
}));

const notFound = vi.hoisted(() => vi.fn(() => {
  throw new Error('NEXT_NOT_FOUND');
}));
vi.mock('next/navigation', () => ({ notFound }));

import CompanionPage from '../page';

const VIEW = {
  companion: { species: 'fox', name: null, stage: 'egg', hatched_at: null },
  competencies: [
    { code: 'H_ROOK', title_en: 'The Rook', title_ru: 'Ладья', title_kk: 'Тура', progress: 1, demonstrated: true },
    { code: 'H_KING', title_en: 'The King', title_ru: 'Король', title_kk: 'Патша', progress: 0, demonstrated: false },
  ],
  hatch_ready: false,
  hatch_progress: 0.5,
};

function renderAt(locale: string, messages: Record<string, unknown>) {
  return render(
    <NextIntlClientProvider locale={locale} messages={messages}>
      <CompanionPage />
    </NextIntlClientProvider>,
  );
}

beforeEach(() => {
  flags.on = true;
  notFound.mockClear();
  global.fetch = vi.fn(() =>
    Promise.resolve(new Response(JSON.stringify(VIEW), { status: 200 })),
  ) as unknown as typeof fetch;
});
afterEach(() => cleanup());

describe('CompanionPage flag-off invariant', () => {
  it('404s and renders nothing companion-related (incl. the hatch reveal) when the flag is off', () => {
    flags.on = false;
    expect(() => renderAt('en', en as Record<string, unknown>)).toThrow('NEXT_NOT_FOUND');
    expect(notFound).toHaveBeenCalled();
    expect(screen.queryByText(en.companion.title)).toBeNull();
    // The hatch CTA / reveal never mounts while dark.
    expect(screen.queryByText(en.companion.hatch.cta)).toBeNull();
    expect(screen.queryByLabelText(en.companion.hatch.nameLabel)).toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
  });
});

describe('CompanionPage Phase 3 — hatch', () => {
  function mockView(view: unknown) {
    global.fetch = vi.fn(() =>
      Promise.resolve(new Response(JSON.stringify(view), { status: 200 })),
    ) as unknown as typeof fetch;
  }

  it('shows the hatch CTA and opens the naming reveal when the egg is ready', async () => {
    mockView({ ...VIEW, hatch_ready: true, hatch_progress: 1 });
    renderAt('en', en as Record<string, unknown>);
    const cta = await screen.findByText(en.companion.hatch.cta);
    fireEvent.click(cta);
    // The reveal mounts on its naming step.
    expect(screen.getByLabelText(en.companion.hatch.nameLabel)).toBeTruthy();
  });

  it('does not show the hatch CTA while the egg is not ready', async () => {
    mockView({ ...VIEW, hatch_ready: false });
    renderAt('en', en as Record<string, unknown>);
    await screen.findByRole('heading', { level: 1, name: en.companion.title });
    expect(screen.queryByText(en.companion.hatch.cta)).toBeNull();
  });

  it('renders the hatched fox with its name and a replay button', async () => {
    mockView({
      ...VIEW,
      companion: { species: 'fox', name: 'Rusty', stage: 'hatched', hatched_at: '2026-10-03T00:00:00Z' },
    });
    renderAt('en', en as Record<string, unknown>);
    expect(await screen.findByText('Rusty')).toBeTruthy();
    expect(screen.getByText(en.companion.hatch.replay)).toBeTruthy();
    expect(screen.getByLabelText(en.companion.hatch.foxAlt.replace('{name}', 'Rusty'))).toBeTruthy();
  });
});

describe('CompanionPage render (flag on)', () => {
  it.each(Object.entries({ en, ru, kz }))('renders the egg + ring for %s', async (locale, messages) => {
    renderAt(locale, messages as Record<string, unknown>);
    const ns = (messages as typeof en).companion;
    expect(await screen.findByRole('heading', { level: 1, name: ns.title })).toBeTruthy();
    // The chosen egg renders with its localized alt text.
    expect(screen.getByLabelText(`${ns.eggAlt.replace('{name}', ns.eggs.fox)}`)).toBeTruthy();
    // Competency titles come from the DB payload, localized client-side.
    const rookTitle = locale === 'ru' ? 'Ладья' : locale === 'kz' ? 'Тура' : 'The Rook';
    expect(screen.getByText(rookTitle)).toBeTruthy();
    expect(notFound).not.toHaveBeenCalled();
  });
});
