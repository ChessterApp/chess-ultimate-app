/**
 * Client for the coach session/board management proxies (see
 * hermes/src/boards.py for the server model). Boards are the session's tabs:
 * the study board plus master games, puzzles and (later) games against the
 * coach, one of them active. Everything here is best-effort: the UI keeps its
 * own state and these calls only make it survive a reload.
 */

export type BoardKind = 'study' | 'puzzle' | 'game' | 'master_game';

export interface BoardRecord {
  id: string;
  session_id: string;
  kind: BoardKind;
  title: string;
  pgn: string;
  fen: string;
  ply: number;
  orientation: 'white' | 'black';
  annotations: {
    arrows?: Array<{ from: string; to: string; brush: string }>;
    highlights?: string[];
    highlight_color?: string | null;
  };
  puzzle?: { puzzle_id?: string; solution?: string[]; fen?: string } | null;
  game_state?: Record<string, unknown> | null;
  source?: Record<string, unknown> | null;
  created_at: number;
  updated_at: number;
}

export interface SessionSummary {
  id: string;
  title: string;
  created_at: number;
  updated_at: number;
  message_count: number;
  board_state: string;
  active_board_id: string | null;
  board_count: number;
  preview: string;
}

async function call<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      credentials: 'include',
    });
    if (!res.ok) return null;
    return (await res.json()) as T;
  } catch {
    return null;
  }
}

export const coachApi = {
  listSessions: () => call<SessionSummary[]>('/api/coach/sessions'),

  createSession: (title?: string) =>
    call<SessionSummary>('/api/coach/sessions', { method: 'POST', body: JSON.stringify({ title }) }),

  updateSession: (id: string, patch: { title?: string; active_board_id?: string }) =>
    call<SessionSummary>(`/api/coach/sessions/${encodeURIComponent(id)}`, {
      method: 'PATCH',
      body: JSON.stringify(patch),
    }),

  deleteSession: (id: string) =>
    call<{ deleted: string }>(`/api/coach/sessions/${encodeURIComponent(id)}`, { method: 'DELETE' }),

  listBoards: (sessionId: string) =>
    call<{ active_board_id: string | null; boards: BoardRecord[] }>(
      `/api/coach/sessions/${encodeURIComponent(sessionId)}/boards`,
    ),

  createBoard: (
    sessionId: string,
    body: {
      kind: BoardKind;
      title?: string;
      pgn?: string;
      fen?: string;
      ply?: number;
      orientation?: 'white' | 'black';
      source?: Record<string, unknown>;
      activate?: boolean;
    },
  ) =>
    call<BoardRecord>(`/api/coach/sessions/${encodeURIComponent(sessionId)}/boards`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  updateBoard: (
    sessionId: string,
    boardId: string,
    patch: {
      title?: string;
      pgn?: string;
      fen?: string;
      position?: string;
      ply?: number;
      orientation?: 'white' | 'black';
      annotations?: BoardRecord['annotations'];
      active?: boolean;
    },
  ) =>
    call<BoardRecord>(
      `/api/coach/sessions/${encodeURIComponent(sessionId)}/boards/${encodeURIComponent(boardId)}`,
      { method: 'PATCH', body: JSON.stringify(patch) },
    ),

  deleteBoard: (sessionId: string, boardId: string) =>
    call<{ deleted: string; active_board_id: string | null }>(
      `/api/coach/sessions/${encodeURIComponent(sessionId)}/boards/${encodeURIComponent(boardId)}`,
      { method: 'DELETE' },
    ),

  loadMessages: (sessionId: string) =>
    call<{ messages: Array<{ role: 'user' | 'assistant'; content: string; timestamp: number; source: string }> }>(
      `/api/coach/sessions/${encodeURIComponent(sessionId)}/messages`,
    ),
};
