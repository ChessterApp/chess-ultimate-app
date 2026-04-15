/**
 * @vitest-environment jsdom
 *
 * Tests for useOpeningRepertoire PowerSync integration path.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ─── Feature flag mock ──────────────────

let mockLocalFirstRepertoire = true;
vi.mock('@/lib/feature-flags', () => ({
  get LOCAL_FIRST_REPERTOIRE() { return mockLocalFirstRepertoire; },
}));

// ─── Clerk mock ─────────────────────────

const mockGetToken = vi.fn().mockResolvedValue('test-token');
vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({
    getToken: mockGetToken,
    userId: 'user-123',
  }),
}));

// ─── API mock ───────────────────────────

const mockApiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => mockApiFetch(...args),
}));

// ─── PowerSync context mock ─────────────

const mockExecute = vi.fn();
const mockDatabase = { execute: mockExecute };
const mockCollections = {
  repertoires: { id: 'repertoires-collection' },
  repertoireNodes: { id: 'repertoire-nodes-collection' },
};

vi.mock('@/lib/powersync/PowerSyncProvider', () => ({
  usePowerSyncContext: () => ({
    database: mockDatabase,
    collections: mockCollections,
    isReady: true,
  }),
}));

// ─── useLiveQuery mock ──────────────────

// We need to support multiple live queries — one for repertoires, one for nodes
let liveQueryCallCount = 0;
const mockRepertoireData = vi.fn().mockReturnValue([]);
const mockNodeData = vi.fn().mockReturnValue([]);

vi.mock('@tanstack/react-db', () => ({
  useLiveQuery: () => {
    liveQueryCallCount++;
    // First call = repertoires, second call = nodes
    if (liveQueryCallCount % 2 === 1) {
      return { data: mockRepertoireData(), isLoading: false, isReady: true };
    }
    return { data: mockNodeData(), isLoading: false, isReady: true };
  },
}));

vi.mock('@tanstack/db', () => ({
  eq: vi.fn(),
}));

import { useOpeningRepertoire } from '../useOpeningRepertoire';

// ─── Fixtures ───────────────────────────

const REP_ROW = {
  id: 'rep-1',
  name: 'Sicilian Repertoire',
  color: 'b',
  description: 'My Sicilian lines',
  is_primary: 1,
  starting_fen: null,
  starting_move_line: null,
  created_at: '2024-06-01T10:00:00Z',
  updated_at: '2024-06-01T10:00:00Z',
};

const ROOT_NODE = {
  id: 'node-root',
  repertoire_id: 'rep-1',
  parent_id: null,
  fen: 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1',
  move_san: null,
  move_uci: null,
  move_number: 0,
  is_white_move: null,
  opening_name: 'Starting Position',
  eco_code: null,
  notes: null,
  priority: 0,
  is_critical: 0,
  times_trained: 0,
  times_correct: 0,
  last_trained_at: null,
  next_review_at: null,
  ease_factor: 2.5,
  interval_days: 0,
  created_at: '2024-06-01T10:00:00Z',
  updated_at: '2024-06-01T10:00:00Z',
};

const CHILD_NODE = {
  ...ROOT_NODE,
  id: 'node-e4',
  parent_id: 'node-root',
  fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
  move_san: 'e4',
  move_uci: 'e2e4',
  move_number: 1,
  is_white_move: 1,
};

// ─── Tests ──────────────────────────────

describe('useOpeningRepertoire (PowerSync mode)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    liveQueryCallCount = 0;
    mockLocalFirstRepertoire = true;
    mockRepertoireData.mockReturnValue([]);
    mockNodeData.mockReturnValue([]);
  });

  it('should return empty repertoires when live query has no data', () => {
    const { result } = renderHook(() => useOpeningRepertoire());
    expect(result.current.repertoires).toEqual([]);
    expect(result.current.error).toBeNull();
  });

  it('should return repertoires from live query with correct type conversion', () => {
    mockRepertoireData.mockReturnValue([REP_ROW]);

    const { result } = renderHook(() => useOpeningRepertoire());

    expect(result.current.repertoires).toHaveLength(1);
    const rep = result.current.repertoires[0];
    expect(rep.id).toBe('rep-1');
    expect(rep.name).toBe('Sicilian Repertoire');
    expect(rep.color).toBe('b');
    expect(rep.is_primary).toBe(true); // converted from 1
  });

  it('fetchRepertoires should be a no-op in PowerSync mode', async () => {
    const { result } = renderHook(() => useOpeningRepertoire());

    await act(async () => {
      await result.current.fetchRepertoires();
    });

    // No API calls
    expect(mockApiFetch).not.toHaveBeenCalled();
  });

  it('should create repertoire via API', async () => {
    mockApiFetch.mockResolvedValueOnce({
      repertoire: { id: 'rep-new', name: 'New', color: 'w' },
    });

    const { result } = renderHook(() => useOpeningRepertoire());

    let created: any;
    await act(async () => {
      created = await result.current.createRepertoire('New', 'w');
    });

    expect(created.id).toBe('rep-new');
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/openings/repertoires',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('should update repertoire via PowerSync local write', async () => {
    const { result } = renderHook(() => useOpeningRepertoire());

    await act(async () => {
      await result.current.updateRepertoire('rep-1', { name: 'Updated Name' });
    });

    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE repertoires SET'),
      expect.arrayContaining(['Updated Name']),
    );
  });

  it('should delete repertoire and its nodes via PowerSync', async () => {
    const { result } = renderHook(() => useOpeningRepertoire());

    await act(async () => {
      await result.current.deleteRepertoire('rep-1');
    });

    expect(mockExecute).toHaveBeenCalledWith(
      'DELETE FROM repertoire_nodes WHERE repertoire_id = ?',
      ['rep-1'],
    );
    expect(mockExecute).toHaveBeenCalledWith(
      'DELETE FROM repertoires WHERE id = ?',
      ['rep-1'],
    );
  });

  it('should update node via PowerSync local write', async () => {
    const { result } = renderHook(() => useOpeningRepertoire());

    await act(async () => {
      await result.current.updateNode('node-e4', { notes: 'Critical move', isCritical: true });
    });

    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE repertoire_nodes SET'),
      expect.arrayContaining(['Critical move', 1]), // notes and is_critical=1
    );
  });

  it('should delete node via PowerSync', async () => {
    const { result } = renderHook(() => useOpeningRepertoire());

    await act(async () => {
      await result.current.deleteNode('node-e4');
    });

    expect(mockExecute).toHaveBeenCalledWith(
      'DELETE FROM repertoire_nodes WHERE id = ?',
      ['node-e4'],
    );
  });

  it('should add node via API (server handles validation)', async () => {
    mockApiFetch.mockResolvedValueOnce(CHILD_NODE);

    const { result } = renderHook(() => useOpeningRepertoire());

    let node: any;
    await act(async () => {
      node = await result.current.addNode('node-root', 'e4', 'e2e4', CHILD_NODE.fen);
    });

    expect(node.id).toBe('node-e4');
    expect(mockApiFetch).toHaveBeenCalledWith(
      '/api/openings/nodes',
      expect.objectContaining({ method: 'POST' }),
    );
  });

  it('should fetch games by position via API (server-side TWIC query)', async () => {
    mockApiFetch.mockResolvedValueOnce({
      games: [{ id: 1, white: 'Carlsen', black: 'Nepo' }],
      total: 1,
      indexed: true,
    });

    const { result } = renderHook(() => useOpeningRepertoire());

    let data: any;
    await act(async () => {
      data = await result.current.fetchGamesByPosition('rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1');
    });

    expect(data.games).toHaveLength(1);
    expect(mockApiFetch).toHaveBeenCalled();
  });

  it('should keep training operations server-side', async () => {
    mockApiFetch.mockResolvedValueOnce({ nodes: [] });

    const { result } = renderHook(() => useOpeningRepertoire());

    await act(async () => {
      await result.current.getDueNodes('rep-1');
    });

    expect(mockApiFetch).toHaveBeenCalledWith(
      expect.stringContaining('/api/openings/training/due'),
      expect.any(Object),
    );
  });

  it('should import PGN via API', async () => {
    mockApiFetch.mockResolvedValueOnce({ imported: 5, skipped: 0, errors: [] });

    const { result } = renderHook(() => useOpeningRepertoire());

    let importResult: any;
    await act(async () => {
      importResult = await result.current.importPgn('rep-1', '1. e4 e5 2. Nf3 Nc6');
    });

    expect(importResult.imported).toBe(5);
  });
});
