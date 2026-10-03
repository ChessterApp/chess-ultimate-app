/**
 * @vitest-environment jsdom
 *
 * Companion page: the flag-off invariant (nothing companion-related renders; the
 * route 404s) and a per-locale render smoke test of the egg + competency ring.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import React from 'react';
import { cleanup, render, screen } from '@testing-library/react';
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
  it('404s and renders nothing companion-related when the flag is off', () => {
    flags.on = false;
    expect(() => renderAt('en', en as Record<string, unknown>)).toThrow('NEXT_NOT_FOUND');
    expect(notFound).toHaveBeenCalled();
    expect(screen.queryByText(en.companion.title)).toBeNull();
    expect(global.fetch).not.toHaveBeenCalled();
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
