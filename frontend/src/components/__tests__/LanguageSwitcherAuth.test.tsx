// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent } from '@testing-library/react';
import React from 'react';

// The provider owns the switch (see LocaleProvider.test); here we only check
// the switcher drives it.
const localeSwitch = vi.hoisted(() => ({
  switchLocale: vi.fn(),
  prefetchLocale: vi.fn(),
  isSwitching: false,
}));
vi.mock('@/components/LocaleProvider', () => ({ useLocaleSwitch: () => localeSwitch }));
const trackMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics/events', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics/events')>()),
  track: trackMock,
}));
const localeState = vi.hoisted(() => ({ current: 'en' }));
vi.mock('next-intl', () => ({ useLocale: () => localeState.current }));

import LanguageSwitcher from '@/components/LanguageSwitcher';

const trigger = () => screen.getByRole('button', { name: 'Change language' });

describe('LanguageSwitcher', () => {
  beforeEach(() => {
    cleanup();
    localeSwitch.switchLocale.mockClear();
    localeSwitch.prefetchLocale.mockClear();
    localeSwitch.isSwitching = false;
    trackMock.mockClear();
    localeState.current = 'en';
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, pathname: '/onboarding' },
    });
  });

  it('renders a compact pill showing the live locale code', () => {
    const { rerender } = render(<LanguageSwitcher variant="auth" />);
    expect(trigger().textContent).toContain('EN');
    localeState.current = 'ru';
    rerender(<LanguageSwitcher variant="auth" />);
    expect(trigger().textContent).toContain('RU');
  });

  it('switches through the provider and closes the dropdown at once', () => {
    render(<LanguageSwitcher variant="auth" />);
    fireEvent.click(trigger());
    fireEvent.click(screen.getByText('Русский'));

    expect(screen.queryByText('Қазақша')).toBeNull();
    expect(localeSwitch.switchLocale).toHaveBeenCalledTimes(1);
    expect(localeSwitch.switchLocale).toHaveBeenCalledWith('ru');
  });

  it.each(['default', 'minimal'] as const)('%s variant switches through the provider', (variant) => {
    render(<LanguageSwitcher variant={variant} />);
    fireEvent.click(trigger());
    fireEvent.click(screen.getAllByRole('button').at(-1)!);
    expect(localeSwitch.switchLocale).toHaveBeenCalledWith('kz');
  });

  it('prefetches the other locales on hover, focus and open', () => {
    render(<LanguageSwitcher variant="auth" />);
    fireEvent.mouseEnter(trigger());
    expect(localeSwitch.prefetchLocale.mock.calls).toEqual([['ru'], ['kz']]);
    localeSwitch.prefetchLocale.mockClear();
    fireEvent.focus(trigger());
    expect(localeSwitch.prefetchLocale).toHaveBeenCalledTimes(2);
    localeSwitch.prefetchLocale.mockClear();
    fireEvent.click(trigger());
    expect(localeSwitch.prefetchLocale).toHaveBeenCalledTimes(2);
  });

  it('shows a busy, disabled trigger while the messages load', () => {
    localeSwitch.isSwitching = true;
    render(<LanguageSwitcher variant="auth" />);
    expect(trigger().getAttribute('aria-busy')).toBe('true');
    expect((trigger() as HTMLButtonElement).disabled).toBe(true);
    fireEvent.click(trigger());
    expect(screen.queryByText('Қазақша')).toBeNull();
  });

  it('picking the current locale just closes the dropdown', async () => {
    render(<LanguageSwitcher variant="auth" />);
    fireEvent.click(trigger());
    fireEvent.click(screen.getByText('English'));
    expect(screen.queryByText('Русский')).toBeNull();
    expect(localeSwitch.switchLocale).not.toHaveBeenCalled();
    expect(trackMock).not.toHaveBeenCalled();
  });

  it('tracks language_switched with from / to / surface', () => {
    render(<LanguageSwitcher variant="auth" />);
    fireEvent.click(trigger());
    fireEvent.click(screen.getByText('Русский'));
    expect(trackMock).toHaveBeenCalledWith('language_switched', {
      from: 'en',
      to: 'ru',
      surface: 'onboarding',
    });
  });
});
