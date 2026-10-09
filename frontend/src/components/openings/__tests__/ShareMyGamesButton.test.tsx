// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import React from 'react';

// next-intl: echo the key so assertions stay locale-independent.
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

// Clerk: always hand back a token.
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: () => Promise.resolve('clerk-tok') }),
}));

// Collection share endpoints.
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import ShareMyGamesButton, { buildCollectionShareUrl } from '../ShareMyGamesButton';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

const writeText = vi.fn().mockResolvedValue(undefined);

beforeEach(() => {
  mockApiFetch.mockReset();
  writeText.mockClear();
  // jsdom has no clipboard by default; shareOrCopyGame falls to clipboard
  // because navigator.share is absent.
  Object.defineProperty(navigator, 'clipboard', {
    value: { writeText },
    configurable: true,
  });
});

describe('buildCollectionShareUrl', () => {
  it('builds a /g/c/<token> collection link', () => {
    expect(buildCollectionShareUrl('https://chesster.io', 'abc123')).toBe(
      'https://chesster.io/g/c/abc123',
    );
  });
});

describe('ShareMyGamesButton', () => {
  it('mints a token on open and shows the share link', async () => {
    mockApiFetch.mockResolvedValueOnce({ token: 'tok123' });
    render(<ShareMyGamesButton />);

    fireEvent.click(screen.getByText('button'));

    const input = await screen.findByDisplayValue(/\/g\/c\/tok123$/);
    expect(input).toBeTruthy();
    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/games/collection/share'),
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('shows a loading spinner while minting', async () => {
    let resolvePost!: (v: { token: string }) => void;
    mockApiFetch.mockReturnValueOnce(new Promise((r) => { resolvePost = r; }));
    render(<ShareMyGamesButton />);

    fireEvent.click(screen.getByText('button'));
    expect(screen.getByRole('progressbar')).toBeTruthy();

    resolvePost({ token: 'tok123' });
    await screen.findByDisplayValue(/\/g\/c\/tok123$/);
  });

  it('copies the link to the clipboard', async () => {
    mockApiFetch.mockResolvedValueOnce({ token: 'tok123' });
    render(<ShareMyGamesButton />);

    fireEvent.click(screen.getByText('button'));
    await screen.findByDisplayValue(/\/g\/c\/tok123$/);

    fireEvent.click(screen.getByText('copy'));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/\/g\/c\/tok123$/));
    });
    expect(await screen.findByText('copied')).toBeTruthy();
  });

  it('revokes the link and offers to regenerate', async () => {
    mockApiFetch.mockResolvedValueOnce({ token: 'tok123' }); // POST mint
    render(<ShareMyGamesButton />);

    fireEvent.click(screen.getByText('button'));
    await screen.findByDisplayValue(/\/g\/c\/tok123$/);

    mockApiFetch.mockResolvedValueOnce(''); // DELETE revoke (204, empty body)
    fireEvent.click(screen.getByText('revoke'));

    expect(await screen.findByText('revoked')).toBeTruthy();
    expect(mockApiFetch).toHaveBeenLastCalledWith(
      expect.stringContaining('/api/games/collection/share'),
      expect.objectContaining({ method: 'DELETE' }),
    );
    expect(screen.getByText('regenerate')).toBeTruthy();
  });

  it('regenerates a new token after revoke', async () => {
    mockApiFetch.mockResolvedValueOnce({ token: 'tok123' }); // mint
    render(<ShareMyGamesButton />);
    fireEvent.click(screen.getByText('button'));
    await screen.findByDisplayValue(/\/g\/c\/tok123$/);

    mockApiFetch.mockResolvedValueOnce(''); // revoke
    fireEvent.click(screen.getByText('revoke'));
    await screen.findByText('revoked');

    mockApiFetch.mockResolvedValueOnce({ token: 'tok999' }); // regenerate
    fireEvent.click(screen.getByText('regenerate'));

    expect(await screen.findByDisplayValue(/\/g\/c\/tok999$/)).toBeTruthy();
  });

  it('shows an error state when minting fails', async () => {
    mockApiFetch.mockRejectedValueOnce(new Error('boom'));
    render(<ShareMyGamesButton />);

    fireEvent.click(screen.getByText('button'));

    expect(await screen.findByText('error')).toBeTruthy();
  });
});
