// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, act } from '@testing-library/react';
import React, { useEffect } from 'react';
import { useLocale, useTranslations, type AbstractIntlMessages } from 'next-intl';

// Small stand-ins for the real catalogues; kz fails like an offline chunk.
vi.mock('../../../messages/ru.json', () => ({ default: { t: { hi: 'Привет, {appName}' } } }));
vi.mock('../../../messages/en.json', () => ({ default: { t: { hi: 'Hello, {appName}' } } }));
vi.mock('../../../messages/kz.json', () => { throw new Error('offline'); });
const refresh = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh }) }));
const persist = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
vi.mock('@/lib/preferred-locale', () => ({ persistPreferredLocale: persist }));

import LocaleProvider, { useLocaleSwitch } from '@/components/LocaleProvider';
import { OrganizationProvider, type Organization } from '@/contexts/OrganizationContext';

const EN: AbstractIntlMessages = { t: { hi: 'Hello, Chess Empire' } };
const org = { name: 'Chess Empire' } as Organization;

const probe = {} as { api: ReturnType<typeof useLocaleSwitch> };
const renders: { locale: string; cookie: string }[] = [];

function Probe() {
  const t = useTranslations('t');
  const locale = useLocale();
  const localeSwitch = useLocaleSwitch();
  useEffect(() => { probe.api = localeSwitch; });
  renders.push({ locale, cookie: document.cookie });
  return <p data-testid="text">{locale}:{t('hi')}</p>;
}

function tree(serverLocale: string, serverMessages: AbstractIntlMessages) {
  return (
    <OrganizationProvider org={org}>
      <LocaleProvider serverLocale={serverLocale} serverMessages={serverMessages} timeZone="UTC">
        <Probe />
      </LocaleProvider>
    </OrganizationProvider>
  );
}

const text = () => screen.getByTestId('text').textContent;

describe('LocaleProvider', () => {
  const reload = vi.fn();

  beforeEach(() => {
    cleanup();
    refresh.mockClear();
    persist.mockClear();
    reload.mockClear();
    renders.length = 0;
    document.cookie = 'NEXT_LOCALE=; path=/; max-age=0';
    document.documentElement.lang = 'en';
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload },
    });
  });

  it('swaps the text client-side with the org name substituted, then refreshes once', async () => {
    render(tree('en', EN));
    expect(text()).toBe('en:Hello, Chess Empire');

    await act(() => probe.api.switchLocale('ru'));

    expect(text()).toBe('ru:Привет, Chess Empire');
    expect(document.documentElement.lang).toBe('ru');
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(reload).not.toHaveBeenCalled();
    expect(persist).toHaveBeenCalledWith('ru');
  });

  it('writes the cookie before the locale changes', async () => {
    // The swap sets <html lang> next to the state update: see what the cookie was then.
    const cookieAtSwap: string[] = [];
    const html = document.documentElement;
    Object.defineProperty(html, 'lang', {
      configurable: true,
      set(value: string) { cookieAtSwap.push(`${value}|${document.cookie}`); },
      get() { return ''; },
    });
    try {
      render(tree('en', EN));
      await act(() => probe.api.switchLocale('ru'));
    } finally {
      delete (html as unknown as { lang?: string }).lang;
    }

    expect(cookieAtSwap).toEqual(['ru|NEXT_LOCALE=ru']);
    expect(renders.find((r) => r.locale === 'ru')?.cookie).toContain('NEXT_LOCALE=ru');
  });

  it('ignores a stale server payload for the old locale and adopts the matching one', async () => {
    const { rerender } = render(tree('en', EN));
    await act(() => probe.api.switchLocale('ru'));

    // A render started before the switch lands with fresh-but-old messages.
    rerender(tree('en', { t: { hi: 'Hello again' } }));
    expect(text()).toBe('ru:Привет, Chess Empire');

    rerender(tree('ru', { t: { hi: 'Привет с сервера' } }));
    expect(text()).toBe('ru:Привет с сервера');
  });

  it('adopts a server-driven locale change when no switch is pending', () => {
    const { rerender } = render(tree('en', EN));
    rerender(tree('ru', { t: { hi: 'Сохранённый язык' } }));
    expect(text()).toBe('ru:Сохранённый язык');
  });

  it('falls back to cookie + refresh when the messages fail to load', async () => {
    render(tree('en', EN));
    await act(() => probe.api.switchLocale('kz'));

    expect(text()).toBe('en:Hello, Chess Empire');
    expect(document.cookie).toContain('NEXT_LOCALE=kz');
    expect(refresh).toHaveBeenCalledTimes(1);
    expect(probe.api.isSwitching).toBe(false);
  });

  it('reports isSwitching only while the messages load', async () => {
    render(tree('en', EN));
    let done!: Promise<void>;
    act(() => { done = probe.api.switchLocale('ru'); });
    expect(probe.api.isSwitching).toBe(true);
    await act(() => done);
    expect(probe.api.isSwitching).toBe(false);
  });
});
