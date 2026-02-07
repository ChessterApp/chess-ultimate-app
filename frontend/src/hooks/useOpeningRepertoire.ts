/**
 * useOpeningRepertoire — Hook for managing opening repertoire data
 * Communicates with /api/openings backend endpoints
 */

import { useState, useCallback } from 'react';

const API_BASE = '/api/openings';

// ─── Types ───────────────────────────────

export interface Repertoire {
  id: string;
  name: string;
  color: 'w' | 'b';
  description: string | null;
  is_primary: boolean;
  starting_fen: string | null;
  starting_move_line: string | null;
  created_at: string;
  updated_at: string;
  node_count?: number;
}

export interface OpeningNode {
  id: string;
  repertoire_id: string;
  parent_id: string | null;
  fen: string;
  move_san: string | null;
  move_uci: string | null;
  move_number: number;
  is_white_move: boolean | null;
  opening_name: string | null;
  eco_code: string | null;
  notes: string | null;
  priority: number;
  is_critical: boolean;
  times_trained: number;
  times_correct: number;
  last_trained_at: string | null;
  next_review_at: string | null;
  ease_factor: number;
  interval_days: number;
  created_at: string;
  updated_at: string;
  children?: OpeningNode[];
  arrows?: ArrowAnnotation[];
}

export interface ArrowAnnotation {
  id: string;
  node_id: string;
  from_square: string;
  to_square: string;
  color: string;
  opacity: number;
}

export interface GameLink {
  id: string;
  node_id: string;
  game_source: 'internal' | 'lichess' | 'chesscom' | 'pgn' | 'user';
  game_id: string | null;
  game_pgn: string | null;
  white_player: string | null;
  black_player: string | null;
  white_elo: number | null;
  black_elo: number | null;
  result: string | null;
  date_played: string | null;
  event_name: string | null;
  created_at: string;
}

export interface ImportPgnResult {
  imported: number;
  skipped: number;
  errors: string[];
  nodes?: Partial<OpeningNode>[];
}

export interface TrainingStats {
  total_nodes: number;
  trained_nodes: number;
  due_nodes: number;
  total_reviews: number;
  accuracy: number;
}

export interface GameSearchResult {
  id: string | number;
  source: string;
  white: string;
  black: string;
  white_elo: number | null;
  black_elo: number | null;
  result: string;
  date: string;
  eco: string | null;
  opening: string | null;
  event: string | null;
  pgn?: string;
  url?: string;
}

// ─── Helper: build auth headers ──────────

function getHeaders(): HeadersInit {
  // Auth is disabled in local development — use a dummy JWT
  // In production, get token from Clerk's useAuth().getToken()
  const token = 'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJsb2NhbF91c2VyIn0.FakeTokenForLocalDev';
  return {
    'Content-Type': 'application/json',
    'Authorization': `Bearer ${token}`,
  };
}

async function apiFetch<T>(path: string, options?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: getHeaders(),
    ...options,
  });

  if (!res.ok) {
    const body = await res.json().catch(() => ({ error: res.statusText }));
    throw new Error(body.error || `API error ${res.status}`);
  }

  // Handle PGN (text) responses
  const ct = res.headers.get('Content-Type') || '';
  if (ct.includes('chess-pgn') || ct.includes('text/plain')) {
    return (await res.text()) as unknown as T;
  }

  return res.json();
}

// ─── Hook ────────────────────────────────

export function useOpeningRepertoire() {
  const [repertoires, setRepertoires] = useState<Repertoire[]>([]);
  const [currentTree, setCurrentTree] = useState<OpeningNode | null>(null);
  const [loading, setLoading] = useState(false);
  const [treeLoading, setTreeLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  // ── Repertoire CRUD ──────────

  const fetchRepertoires = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await apiFetch<{ repertoires: Repertoire[] }>('/repertoires');
      setRepertoires(data.repertoires);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, []);

  const createRepertoire = useCallback(async (
    name: string,
    color: 'w' | 'b',
    opts?: { description?: string; startingFen?: string; startingMoveLine?: string }
  ): Promise<Repertoire> => {
    const data = await apiFetch<{ repertoire: Repertoire }>('/repertoires', {
      method: 'POST',
      body: JSON.stringify({ name, color, ...opts }),
    });
    await fetchRepertoires();
    return data.repertoire;
  }, [fetchRepertoires]);

  const updateRepertoire = useCallback(async (id: string, updates: Partial<Repertoire>) => {
    await apiFetch(`/repertoires/${id}`, {
      method: 'PUT',
      body: JSON.stringify(updates),
    });
    await fetchRepertoires();
  }, [fetchRepertoires]);

  const deleteRepertoire = useCallback(async (id: string) => {
    await apiFetch(`/repertoires/${id}`, { method: 'DELETE' });
    await fetchRepertoires();
  }, [fetchRepertoires]);

  // ── Tree ──────────────────────

  const fetchTree = useCallback(async (repertoireId: string) => {
    setTreeLoading(true);
    try {
      const data = await apiFetch<{ repertoire: Repertoire; tree: OpeningNode }>(`/repertoires/${repertoireId}`);
      setCurrentTree(data.tree);
    } catch (e: any) {
      setError(e.message);
    } finally {
      setTreeLoading(false);
    }
  }, []);

  const addNode = useCallback(async (
    parentId: string,
    moveSan: string,
    moveUci: string,
    newFen: string
  ): Promise<OpeningNode> => {
    const data = await apiFetch<OpeningNode>('/nodes', {
      method: 'POST',
      body: JSON.stringify({ parentId, moveSan, moveUci, newFen }),
    });
    return data;
  }, []);

  const updateNode = useCallback(async (
    nodeId: string,
    data: { notes?: string; priority?: number; isCritical?: boolean }
  ) => {
    await apiFetch(`/nodes/${nodeId}`, {
      method: 'PUT',
      body: JSON.stringify(data),
    });
  }, []);

  const deleteNode = useCallback(async (nodeId: string) => {
    await apiFetch(`/nodes/${nodeId}`, { method: 'DELETE' });
  }, []);

  // ── Starting position ────────

  const setStartingPosition = useCallback(async (
    repertoireId: string,
    fen: string,
    moveLine?: string
  ) => {
    await apiFetch(`/repertoires/${repertoireId}/starting-position`, {
      method: 'PUT',
      body: JSON.stringify({ fen, moveLine }),
    });
  }, []);

  // ── PGN import/export ────────

  const importPgn = useCallback(async (
    repertoireId: string,
    pgn: string,
    maxPly?: number
  ): Promise<ImportPgnResult> => {
    return apiFetch(`/repertoires/${repertoireId}/import`, {
      method: 'POST',
      body: JSON.stringify({ pgn, maxPly: maxPly || 30 }),
    });
  }, []);

  const exportPgn = useCallback(async (
    repertoireId: string,
    includeNotes?: boolean
  ): Promise<string> => {
    const notes = includeNotes !== false ? 'true' : 'false';
    return apiFetch<string>(`/repertoires/${repertoireId}/pgn?include_notes=${notes}`);
  }, []);

  // ── Arrows ───────────────────

  const addArrow = useCallback(async (
    nodeId: string,
    fromSquare: string,
    toSquare: string,
    color?: string
  ): Promise<ArrowAnnotation> => {
    return apiFetch(`/nodes/${nodeId}/arrows`, {
      method: 'POST',
      body: JSON.stringify({ fromSquare, toSquare, color: color || 'green' }),
    });
  }, []);

  const deleteArrow = useCallback(async (nodeId: string, arrowId: string) => {
    await apiFetch(`/nodes/${nodeId}/arrows/${arrowId}`, { method: 'DELETE' });
  }, []);

  // ── Game search & linking ────

  const searchGames = useCallback(async (
    source: string,
    fen: string,
    opts?: { username?: string; maxGames?: number }
  ): Promise<GameSearchResult[]> => {
    const params = new URLSearchParams({ source, fen });
    if (opts?.username) params.set('username', opts.username);
    if (opts?.maxGames) params.set('max_games', String(opts.maxGames));
    const data = await apiFetch<{ games: GameSearchResult[] }>(`/games/search?${params}`);
    return data.games;
  }, []);

  const searchGamesStream = useCallback((
    source: string,
    fen: string,
    opts: { eco?: string; minRating?: number; username?: string; maxGames?: number } | undefined,
    onGame: (game: GameSearchResult) => void,
    onProgress: (progress: { checked: number; found: number }) => void
  ): (() => void) => {
    const params = new URLSearchParams({ source, fen });
    if (opts?.eco) params.set('eco', opts.eco);
    if (opts?.minRating) params.set('min_rating', String(opts.minRating));
    if (opts?.username) params.set('username', opts.username);
    if (opts?.maxGames) params.set('max_games', String(opts.maxGames));

    const headers = getHeaders();
    const controller = new AbortController();

    fetch(`${API_BASE}/games/search/stream?${params}`, {
      headers,
      signal: controller.signal,
    }).then(async (res) => {
      if (!res.body) return;
      const reader = res.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const event = JSON.parse(line.slice(6));
              if (event.type === 'game') {
                onGame(event.game);
              }
              if (event.type === 'progress' || event.type === 'game') {
                onProgress({ checked: event.checked || 0, found: event.found || 0 });
              }
            } catch { /* ignore parse errors */ }
          }
        }
      }
    }).catch(() => { /* aborted or network error */ });

    return () => controller.abort();
  }, []);

  const linkGame = useCallback(async (nodeId: string, data: Partial<GameLink>) => {
    await apiFetch(`/nodes/${nodeId}/games`, {
      method: 'POST',
      body: JSON.stringify({
        gameSource: data.game_source,
        gameId: data.game_id,
        gamePgn: data.game_pgn,
        whitePlayer: data.white_player,
        blackPlayer: data.black_player,
        whiteElo: data.white_elo,
        blackElo: data.black_elo,
        result: data.result,
        datePlayed: data.date_played,
        eventName: data.event_name,
      }),
    });
  }, []);

  const getNodeGames = useCallback(async (nodeId: string): Promise<GameLink[]> => {
    const data = await apiFetch<{ games: GameLink[] }>(`/nodes/${nodeId}/games`);
    return data.games;
  }, []);

  const deleteGameLink = useCallback(async (gameLinkId: string) => {
    await apiFetch(`/games/${gameLinkId}`, { method: 'DELETE' });
  }, []);

  // ── Training ─────────────────

  const getDueNodes = useCallback(async (
    repertoireId?: string,
    limit?: number
  ): Promise<OpeningNode[]> => {
    const params = new URLSearchParams();
    if (repertoireId) params.set('repertoire_id', repertoireId);
    if (limit) params.set('limit', String(limit));
    const data = await apiFetch<{ nodes: OpeningNode[] }>(`/training/due?${params}`);
    return data.nodes;
  }, []);

  const recordTrainingResult = useCallback(async (
    nodeId: string,
    correct: boolean,
    timeMs?: number
  ) => {
    await apiFetch('/training/result', {
      method: 'POST',
      body: JSON.stringify({ nodeId, correct, timeMs }),
    });
  }, []);

  const getTrainingStats = useCallback(async (
    repertoireId?: string
  ): Promise<TrainingStats> => {
    const params = new URLSearchParams();
    if (repertoireId) params.set('repertoire_id', repertoireId);
    return apiFetch(`/training/stats?${params}`);
  }, []);

  return {
    // Repertoire CRUD
    repertoires,
    loading,
    error,
    fetchRepertoires,
    createRepertoire,
    updateRepertoire,
    deleteRepertoire,
    // Tree
    currentTree,
    treeLoading,
    fetchTree,
    addNode,
    updateNode,
    deleteNode,
    // Starting position
    setStartingPosition,
    // PGN
    importPgn,
    exportPgn,
    // Arrows
    addArrow,
    deleteArrow,
    // Game search
    searchGames,
    searchGamesStream,
    linkGame,
    getNodeGames,
    deleteGameLink,
    // Training
    getDueNodes,
    recordTrainingResult,
    getTrainingStats,
  };
}
