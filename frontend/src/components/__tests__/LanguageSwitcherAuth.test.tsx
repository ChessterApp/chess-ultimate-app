// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, cleanup, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// Mock the setLocale server action so no next/headers runtime is needed and we
// can assert it's invoked on selection.
const { setLocale } = vi.hoisted(() => ({ setLocale: vi.fn().mockResolvedValue(undefined) }));
vi.mock('@/app/actions/setLocale', () => ({ setLocale }));

import LanguageSwitcher from '@/components/LanguageSwitcher';

describe('LanguageSwitcher auth variant', () => {
  const reload = vi.fn();

  beforeEach(() => {
    cleanup();
    setLocale.mockClear();
    reload.mockClear();
    // window.location.reload is called after the locale changes.
    Object.defineProperty(window, 'location', {
      configurable: true,
      value: { ...window.location, reload },
    });
  });

  it('renders a compact pill showing the current locale code', () => {
    render(<LanguageSwitcher variant="auth" currentLocale="en" />);
    const btn = screen.getByRole('button', { name: 'Change language' });
    expect(btn.textContent).toContain('EN');
  });

  it('opens the dropdown and calls setLocale + reload when a locale is picked', async () => {
    render(<LanguageSwitcher variant="auth" currentLocale="en" />);

    // Open the dropdown.
    fireEvent.click(screen.getByRole('button', { name: 'Change language' }));

    // Pick Russian by its full language name.
    fireEvent.click(screen.getByText('Русский'));

    await waitFor(() => expect(setLocale).toHaveBeenCalledWith('ru'));
    await waitFor(() => expect(reload).toHaveBeenCalled());
  });

  it('persists the pick as preferred_locale on the signed-in Clerk user', async () => {
    const update = vi.fn().mockResolvedValue({});
    (window as unknown as { Clerk?: unknown }).Clerk = { user: { unsafeMetadata: {}, update } };
    try {
      render(<LanguageSwitcher variant="auth" currentLocale="en" />);
      fireEvent.click(screen.getByRole('button', { name: 'Change language' }));
      fireEvent.click(screen.getByText('Қазақша'));

      await waitFor(() => expect(setLocale).toHaveBeenCalledWith('kz'));
      expect(update).toHaveBeenCalledWith({ unsafeMetadata: { preferred_locale: 'kz' } });
      await waitFor(() => expect(reload).toHaveBeenCalled());
    } finally {
      delete (window as unknown as { Clerk?: unknown }).Clerk;
    }
  });
});
