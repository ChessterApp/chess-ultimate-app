// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor, act } from '@testing-library/react';
import React from 'react';

// Mock the setLocale server action so no next/headers runtime is needed and we
// can assert it's invoked on selection.
const { setLocale } = vi.hoisted(() => ({ setLocale: vi.fn() }));
vi.mock('@/app/actions/setLocale', () => ({ setLocale }));
const trackMock = vi.hoisted(() => vi.fn());
vi.mock('@/lib/analytics/events', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@/lib/analytics/events')>()),
  track: trackMock,
}));
const refresh = vi.hoisted(() => vi.fn());
vi.mock('next/navigation', () => ({ useRouter: () => ({ refresh }) }));
const localeState = vi.hoisted(() => ({ current: 'en' }));
vi.mock('next-intl', () => ({ useLocale: () => localeState.current }));

import LanguageSwitcher from '@/components/LanguageSwitcher';

const trigger = () => screen.getByRole('button', { name: 'Change language' });

describe('LanguageSwitcher', () => {
  const reload = vi.fn();

  beforeEach(() => {
    cleanup();
    setLocale.mockReset().mockResolvedValue(undefined);
    refresh.mockClear();
    reload.mockClear();
    trackMock.mockClear();
    localeState.current = 'en';
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, pathname: '/onboarding', reload },
    });
  });

  it('renders a compact pill showing the live locale code', () => {
    const { rerender } = render(<LanguageSwitcher variant="auth" />);
    expect(trigger().textContent).toContain('EN');
    localeState.current = 'ru';
    rerender(<LanguageSwitcher variant="auth" />);
    expect(trigger().textContent).toContain('RU');
  });

  it('switches in place: setLocale then router.refresh, never a reload', async () => {
    render(<LanguageSwitcher variant="auth" />);
    fireEvent.click(trigger());
    fireEvent.click(screen.getByText('Русский'));

    // The dropdown closes immediately.
    expect(screen.queryByText('Қазақша')).toBeNull();
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    expect(setLocale).toHaveBeenCalledWith('ru');
    expect(reload).not.toHaveBeenCalled();
  });

  it.each(['default', 'minimal'] as const)('%s variant refreshes instead of reloading', async (variant) => {
    render(<LanguageSwitcher variant={variant} />);
    fireEvent.click(trigger());
    fireEvent.click(screen.getAllByRole('button').at(-1)!);
    await waitFor(() => expect(refresh).toHaveBeenCalledTimes(1));
    expect(reload).not.toHaveBeenCalled();
  });

  it('shows a busy, disabled trigger while the cookie is being written', async () => {
    let resolve!: () => void;
    setLocale.mockReturnValue(new Promise<void>((r) => { resolve = r; }));
    render(<LanguageSwitcher variant="auth" />);
    fireEvent.click(trigger());
    fireEvent.click(screen.getByText('Русский'));

    expect(trigger().getAttribute('aria-busy')).toBe('true');
    expect((trigger() as HTMLButtonElement).disabled).toBe(true);
    // Clicks are ignored while pending: no dropdown, no second switch.
    fireEvent.click(trigger());
    expect(screen.queryByText('Қазақша')).toBeNull();

    await act(async () => resolve());
    await waitFor(() => expect(trigger().getAttribute('aria-busy')).toBe('false'));
    expect(setLocale).toHaveBeenCalledTimes(1);
    expect(refresh).toHaveBeenCalledTimes(1);
  });

  it('keeps the old locale and recovers when setLocale fails', async () => {
    setLocale.mockRejectedValue(new Error('network'));
    render(<LanguageSwitcher variant="auth" />);
    fireEvent.click(trigger());
    fireEvent.click(screen.getByText('Русский'));

    await waitFor(() => expect(trigger().getAttribute('aria-busy')).toBe('false'));
    expect(refresh).not.toHaveBeenCalled();
    expect(reload).not.toHaveBeenCalled();
    expect(trigger().textContent).toContain('EN');
    // Still usable afterwards.
    fireEvent.click(trigger());
    expect(screen.getByText('Қазақша')).toBeTruthy();
  });

  it('picking the current locale just closes the dropdown', async () => {
    render(<LanguageSwitcher variant="auth" />);
    fireEvent.click(trigger());
    fireEvent.click(screen.getByText('English'));
    expect(screen.queryByText('Русский')).toBeNull();
    expect(setLocale).not.toHaveBeenCalled();
    expect(trackMock).not.toHaveBeenCalled();
  });

  it('tracks language_switched with from / to / surface', async () => {
    render(<LanguageSwitcher variant="auth" />);
    fireEvent.click(trigger());
    fireEvent.click(screen.getByText('Русский'));
    await waitFor(() => expect(setLocale).toHaveBeenCalledWith('ru'));
    expect(trackMock).toHaveBeenCalledWith('language_switched', {
      from: 'en',
      to: 'ru',
      surface: 'onboarding',
    });
  });

  it('persists the pick on the Clerk user without waiting for it', async () => {
    // The Clerk write never settles; the switch must not wait on it.
    const update = vi.fn().mockReturnValue(new Promise(() => {}));
    (window as unknown as { Clerk?: unknown }).Clerk = { user: { unsafeMetadata: {}, update } };
    try {
      render(<LanguageSwitcher variant="auth" />);
      fireEvent.click(trigger());
      fireEvent.click(screen.getByText('Қазақша'));

      await waitFor(() => expect(refresh).toHaveBeenCalled());
      expect(setLocale).toHaveBeenCalledWith('kz');
      expect(update).toHaveBeenCalledWith({ unsafeMetadata: { preferred_locale: 'kz' } });
    } finally {
      delete (window as unknown as { Clerk?: unknown }).Clerk;
    }
  });
});
