// @vitest-environment jsdom
//
// "Share database" shares the SELECTED database through the per-database share
// link (`/database?sdb=<token>`): mint on open, copy, revoke, regenerate.
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, cleanup } from '@testing-library/react';
import React from 'react';

// next-intl: echo the key so assertions stay locale-independent.
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

// Clerk: always hand back a token (stable, like the real getToken).
const getToken = () => Promise.resolve('clerk-tok');
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken }),
}));

// Database endpoints (the real useDatabases hook runs on top of this).
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn() }));

import { apiFetch } from '@/lib/api';
import ShareMyGamesButton from '../ShareMyGamesButton';

const mockApiFetch = apiFetch as unknown as ReturnType<typeof vi.fn>;

const writeText = vi.fn().mockResolvedValue(undefined);

const OPENINGS = { id: 'db-1', name: 'Openings', is_default: false, game_count: 3, share_token: null };
const DEFAULT_DB = { id: 'db-0', name: 'My Games', is_default: true, game_count: 9, share_token: null };

type Handler = (url: string, method: string) => unknown;

/** Route apiFetch calls: the db list GET, then `handler` for share calls. */
function routeApi(handler: Handler, list: unknown[] = [OPENINGS, DEFAULT_DB]) {
  mockApiFetch.mockImplementation((url: string, opts?: RequestInit) => {
    const method = opts?.method ?? 'GET';
    if (url === '/api/databases' && method === 'GET') return Promise.resolve(list);
    return handler(url, method);
  });
}

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

afterEach(() => cleanup());

describe('ShareMyGamesButton (Share database)', () => {
  it('mints a link for the selected database and shows its name', async () => {
    routeApi(() => Promise.resolve({ share_token: 'tok123' }));
    render(<ShareMyGamesButton databaseId="db-1" />);

    fireEvent.click(screen.getByText('button'));

    expect(await screen.findByDisplayValue(/\/database\?sdb=tok123$/)).toBeTruthy();
    expect(screen.getByText('title')).toBeTruthy();
    await screen.findByText('Openings');
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/databases/db-1/share',
      expect.objectContaining({ method: 'POST' }),
    );
    expect(mockApiFetch).not.toHaveBeenCalledWith(
      expect.stringContaining('/api/games/collection/share'),
      expect.anything(),
    );
  });

  it('reuses an existing share token without minting', async () => {
    routeApi(() => Promise.reject(new Error('unexpected')), [{ ...OPENINGS, share_token: 'existing' }]);
    render(<ShareMyGamesButton databaseId="db-1" />);
    await screen.findByText('button');
    await waitFor(() => expect(mockApiFetch).toHaveBeenCalledTimes(1)); // list loaded

    fireEvent.click(screen.getByText('button'));

    expect(await screen.findByDisplayValue(/\/database\?sdb=existing$/)).toBeTruthy();
    expect(mockApiFetch).toHaveBeenCalledTimes(1);
  });

  it('renders nothing for the default database (never shareable)', async () => {
    routeApi(() => Promise.resolve({}));
    render(<ShareMyGamesButton databaseId="db-0" />);
    await waitFor(() => expect(screen.queryByText('button')).toBeNull());
  });

  it('shows a loading spinner while minting', async () => {
    let resolvePost!: (v: { share_token: string }) => void;
    routeApi(() => new Promise((r) => { resolvePost = r; }));
    render(<ShareMyGamesButton databaseId="db-1" />);

    fireEvent.click(screen.getByText('button'));
    expect(await screen.findByRole('progressbar')).toBeTruthy();

    resolvePost({ share_token: 'tok123' });
    await screen.findByDisplayValue(/sdb=tok123$/);
  });

  it('copies the link to the clipboard', async () => {
    routeApi(() => Promise.resolve({ share_token: 'tok123' }));
    render(<ShareMyGamesButton databaseId="db-1" />);

    fireEvent.click(screen.getByText('button'));
    await screen.findByDisplayValue(/sdb=tok123$/);

    fireEvent.click(screen.getByText('copy'));

    await waitFor(() => {
      expect(writeText).toHaveBeenCalledWith(expect.stringMatching(/\/database\?sdb=tok123$/));
    });
    expect(await screen.findByText('copied')).toBeTruthy();
  });

  it('revokes the link and regenerates a new one', async () => {
    let next = 'tok123';
    routeApi((_url, method) => Promise.resolve(method === 'DELETE' ? { success: true } : { share_token: next }));
    render(<ShareMyGamesButton databaseId="db-1" />);

    fireEvent.click(screen.getByText('button'));
    await screen.findByDisplayValue(/sdb=tok123$/);

    fireEvent.click(screen.getByText('revoke'));
    expect(await screen.findByText('revoked')).toBeTruthy();
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/databases/db-1/share',
      expect.objectContaining({ method: 'DELETE' }),
    );

    next = 'tok999';
    fireEvent.click(screen.getByText('regenerate'));
    expect(await screen.findByDisplayValue(/sdb=tok999$/)).toBeTruthy();
  });

  it('shows an error state when minting fails', async () => {
    routeApi(() => Promise.reject(new Error('boom')));
    render(<ShareMyGamesButton databaseId="db-1" />);

    fireEvent.click(screen.getByText('button'));

    expect(await screen.findByText('error')).toBeTruthy();
  });
});
