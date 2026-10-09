/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDatabases, type UserDatabase } from '../useDatabases';

// ─── Mocks ───────────────────────────────

const mockGetToken = vi.fn().mockResolvedValue('test-token');

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ getToken: mockGetToken }),
}));

/** Build the shape apiFetch throws: an Error carrying an HTTP `status`. */
function httpError(message: string, status: number): Error {
  return Object.assign(new Error(message), { status });
}

const mockApiFetch = vi.fn();

vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
  ApiError: class ApiError extends Error {
    status: number;
    constructor(message: string, status: number) {
      super(message);
      this.name = 'ApiError';
      this.status = status;
    }
  },
}));

// ─── Fixtures ────────────────────────────

const DEFAULT_DB: UserDatabase = {
  id: 'db-default',
  name: 'My Games',
  is_default: true,
  game_count: 5,
};

const OPENINGS_DB: UserDatabase = {
  id: 'db-openings',
  name: 'Openings',
  is_default: false,
  game_count: 2,
};

// ─── Tests ───────────────────────────────

describe('useDatabases', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockGetToken.mockResolvedValue('test-token');
  });

  it('starts empty', () => {
    const { result } = renderHook(() => useDatabases());
    expect(result.current.databases).toEqual([]);
    expect(result.current.loading).toBe(false);
    expect(result.current.error).toBeNull();
  });

  it('refresh loads the database list', async () => {
    mockApiFetch.mockResolvedValueOnce([DEFAULT_DB, OPENINGS_DB]);
    const { result } = renderHook(() => useDatabases());

    await act(async () => { await result.current.refresh(); });

    expect(result.current.databases).toEqual([DEFAULT_DB, OPENINGS_DB]);
    expect(result.current.error).toBeNull();
    const url = mockApiFetch.mock.calls[0][0] as string;
    expect(url).toBe('/api/databases');
  });

  it('createDatabase appends the new database optimistically', async () => {
    mockApiFetch.mockResolvedValueOnce([DEFAULT_DB]);
    const { result } = renderHook(() => useDatabases());
    await act(async () => { await result.current.refresh(); });

    mockApiFetch.mockResolvedValueOnce(OPENINGS_DB);
    let created: UserDatabase | null = null;
    await act(async () => { created = await result.current.createDatabase('Openings'); });

    expect(created).toEqual(OPENINGS_DB);
    expect(result.current.databases).toEqual([DEFAULT_DB, OPENINGS_DB]);
    const [url, opts] = mockApiFetch.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/databases');
    expect(opts.method).toBe('POST');
  });

  it('surfaces a 409 duplicate as a friendly inline error (no throw)', async () => {
    mockApiFetch.mockResolvedValueOnce([DEFAULT_DB]);
    const { result } = renderHook(() => useDatabases());
    await act(async () => { await result.current.refresh(); });

    mockApiFetch.mockRejectedValueOnce(httpError("dup", 409));
    let created: UserDatabase | null = OPENINGS_DB;
    await act(async () => { created = await result.current.createDatabase('My Games'); });

    expect(created).toBeNull();
    expect(result.current.error).toBe('A database with that name already exists.');
    // The list is unchanged (no optimistic row left behind).
    expect(result.current.databases).toEqual([DEFAULT_DB]);
  });

  it('rejects an empty name without calling the API', async () => {
    const { result } = renderHook(() => useDatabases());
    let created: UserDatabase | null = OPENINGS_DB;
    await act(async () => { created = await result.current.createDatabase('   '); });

    expect(created).toBeNull();
    expect(result.current.error).toBe('Name is required');
    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it('renameDatabase updates optimistically and persists', async () => {
    mockApiFetch.mockResolvedValueOnce([DEFAULT_DB, OPENINGS_DB]);
    const { result } = renderHook(() => useDatabases());
    await act(async () => { await result.current.refresh(); });

    const renamed = { ...OPENINGS_DB, name: 'Repertoire' };
    mockApiFetch.mockResolvedValueOnce(renamed);
    await act(async () => { await result.current.renameDatabase('db-openings', 'Repertoire'); });

    expect(result.current.databases.find(d => d.id === 'db-openings')?.name).toBe('Repertoire');
    const [url, opts] = mockApiFetch.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/databases/db-openings');
    expect(opts.method).toBe('PUT');
  });

  it('rolls back an optimistic rename when the server rejects it', async () => {
    mockApiFetch.mockResolvedValueOnce([DEFAULT_DB, OPENINGS_DB]);
    const { result } = renderHook(() => useDatabases());
    await act(async () => { await result.current.refresh(); });

    mockApiFetch.mockRejectedValueOnce(httpError("dup", 409));
    await act(async () => { await result.current.renameDatabase('db-openings', 'My Games'); });

    // Name reverts to the original after the failed PUT.
    expect(result.current.databases.find(d => d.id === 'db-openings')?.name).toBe('Openings');
    expect(result.current.error).toBe('A database with that name already exists.');
  });

  it('deleteDatabase removes the pill optimistically and calls DELETE', async () => {
    mockApiFetch.mockResolvedValueOnce([DEFAULT_DB, OPENINGS_DB]);
    const { result } = renderHook(() => useDatabases());
    await act(async () => { await result.current.refresh(); });

    mockApiFetch.mockResolvedValueOnce({ success: true });
    let ok = false;
    await act(async () => { ok = await result.current.deleteDatabase('db-openings'); });

    expect(ok).toBe(true);
    expect(result.current.databases).toEqual([DEFAULT_DB]);
    const [url, opts] = mockApiFetch.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/databases/db-openings');
    expect(opts.method).toBe('DELETE');
  });

  it('rolls back the optimistic delete when the server rejects it', async () => {
    mockApiFetch.mockResolvedValueOnce([DEFAULT_DB, OPENINGS_DB]);
    const { result } = renderHook(() => useDatabases());
    await act(async () => { await result.current.refresh(); });

    mockApiFetch.mockRejectedValueOnce(httpError('boom', 500));
    let ok = true;
    await act(async () => { ok = await result.current.deleteDatabase('db-openings'); });

    expect(ok).toBe(false);
    // The pill is restored after the failed DELETE.
    expect(result.current.databases).toEqual([DEFAULT_DB, OPENINGS_DB]);
    expect(result.current.error).toBe('boom');
  });

  it('restoreDatabase POSTs to /restore and refreshes the live list', async () => {
    mockApiFetch.mockResolvedValueOnce([DEFAULT_DB]);
    const { result } = renderHook(() => useDatabases());
    await act(async () => { await result.current.refresh(); });

    // POST /restore resolves, then the hook re-fetches the live list.
    mockApiFetch.mockResolvedValueOnce(OPENINGS_DB);
    mockApiFetch.mockResolvedValueOnce([DEFAULT_DB, OPENINGS_DB]);
    let restored: UserDatabase | null = null;
    await act(async () => { restored = await result.current.restoreDatabase('db-openings'); });

    expect(restored).toEqual(OPENINGS_DB);
    expect(result.current.databases).toEqual([DEFAULT_DB, OPENINGS_DB]);
    const [url, opts] = mockApiFetch.mock.calls[1] as [string, RequestInit];
    expect(url).toBe('/api/databases/db-openings/restore');
    expect(opts.method).toBe('POST');
  });

  it('listDeleted fetches /deleted and returns the rows', async () => {
    const deleted = [
      { id: 'db-openings', name: 'Openings', deleted_at: '2026-01-01T00:00:00+00:00', game_count: 2, days_left: 25 },
    ];
    mockApiFetch.mockResolvedValueOnce(deleted);
    const { result } = renderHook(() => useDatabases());

    let rows: unknown;
    await act(async () => { rows = await result.current.listDeleted(); });

    expect(rows).toEqual(deleted);
    expect(mockApiFetch.mock.calls[0][0]).toBe('/api/databases/deleted');
  });

  it('listDeleted returns [] on error instead of throwing', async () => {
    mockApiFetch.mockRejectedValueOnce(httpError('nope', 500));
    const { result } = renderHook(() => useDatabases());

    let rows: unknown = null;
    await act(async () => { rows = await result.current.listDeleted(); });

    expect(rows).toEqual([]);
  });
});
