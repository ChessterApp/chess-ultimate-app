// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import React from 'react';
import { render, screen } from '@testing-library/react';
import { createTranslator } from 'next-intl';

import en from '../../../../messages/en.json';

vi.mock('next-intl/server', () => ({
  getTranslations: async (namespace: string) =>
    createTranslator({ locale: 'en', messages: en, namespace: namespace as 'privacy' }),
}));

import PrivacyPage, { generateMetadata } from '../page';

describe('/privacy', () => {
  it('renders every section with the support email and delete-account link', async () => {
    render(await PrivacyPage());

    expect(screen.getByRole('heading', { level: 1, name: 'Privacy Policy' })).toBeTruthy();
    expect(screen.getByText('Last updated: 2026-10-12')).toBeTruthy();
    for (const heading of [
      'Who we are',
      'What we collect',
      'Children',
      'Analytics',
      'Who processes your data',
      'Retention and deletion',
      'Contact',
    ]) {
      expect(screen.getByRole('heading', { level: 2, name: heading })).toBeTruthy();
    }
    expect(screen.getByRole('link', { name: 'Delete account' }).getAttribute('href')).toBe('/delete-account');
    expect(screen.getByRole('link', { name: 'support@chesster.io' }).getAttribute('href')).toBe(
      'mailto:support@chesster.io',
    );
    expect(screen.getByText(/never see or store card numbers/)).toBeTruthy();
    expect(screen.queryByText(/TODO legal/)).toBeNull();
  });

  it('exports title and description metadata', async () => {
    expect(await generateMetadata()).toEqual({
      title: 'Privacy Policy — Chesster',
      description: expect.stringContaining('Chesster'),
    });
  });
});
