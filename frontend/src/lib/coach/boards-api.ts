/**
 * Client for the coach session/board management proxies (see
 * hermes/src/boards.py for the server model). Boards are the session's tabs:
 * the study board plus master games, puzzles and (later) games against the
 * coach, one of them active. Everything here is best-effort: the UI keeps its
 * own state and these calls only make it survive a reload.
 */

import { handleRestrictedResponse } from '@/lib/access-fetch';

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

export type GameCommentMode = 'quiet' | 'mistakes' | 'every';

/** What Hermes answers for every game action (start / move / resign / takeback). */
export interface GameStateView {
  board_id: string;
  student_color: 'white' | 'black';
  engine_elo: number;
  comment_mode: GameCommentMode;
  status: 'playing' | 'finished';
  result: '1-0' | '0-1' | '1/2-1/2' | null;
  termination: string | null;
  winner: 'student' | 'engine' | null;
  fen: string;
  pgn: string;
  ply: number;
  moves: string[];
  student_to_move: boolean;
  in_check: boolean;
  /** The student's move just played, with the engine's verdict. */
  student: {
    san: string;
    uci: string;
    verdict: 'ok' | 'inaccuracy' | 'mistake' | 'blunder';
    cp_loss: number;
    eval_after: number;
    best: string | null;
  } | null;
  /** The engine's reply, if the game went on. */
  engine: { san: string; uci: string } | null;
  comment_wanted: boolean;
}

export class CoachApiError extends Error {
  status: number;
  constructor(status: number, message: string) {
    super(message);
    this.status = status;
  }
}

/** Like `call`, but a non-2xx answer throws with Hermes' `detail` (game moves need the reason). */
async function callWithError<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    ...init,
    headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
    credentials: 'include',
  });
  if (!res.ok) {
    // A frozen/expired member hitting a gated coach API is redirected to upgrade.
    if (await handleRestrictedResponse(res)) {
      throw new CoachApiError(res.status, 'MEMBERSHIP_RESTRICTED');
    }
    let message = `HTTP ${res.status}`;
    try {
      const data = (await res.json()) as { detail?: unknown; error?: unknown };
      const d = data.detail ?? data.error;
      if (typeof d === 'string') message = d;
      else if (d && typeof d === 'object' && typeof (d as { detail?: unknown }).detail === 'string') {
        message = (d as { detail: string }).detail;
      }
    } catch {
      // keep the status text
    }
    throw new CoachApiError(res.status, message);
  }
  return (await res.json()) as T;
}

async function call<T>(path: string, init?: RequestInit): Promise<T | null> {
  try {
    const res = await fetch(path, {
      ...init,
      headers: { 'Content-Type': 'application/json', ...(init?.headers ?? {}) },
      credentials: 'include',
    });
    if (!res.ok) {
      await handleRestrictedResponse(res);
      return null;
    }
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

  // ── Game against the coach ──────────────────────────────────────────────
  startGame: (sessionId: string, body: { color: 'white' | 'black' | 'random'; elo: number; comment_mode?: GameCommentMode }) =>
    call<GameStateView>(`/api/coach/sessions/${encodeURIComponent(sessionId)}/game`, {
      method: 'POST',
      body: JSON.stringify(body),
    }),

  gameMove: (sessionId: string, boardId: string, move: string) =>
    callWithError<GameStateView>(
      `/api/coach/sessions/${encodeURIComponent(sessionId)}/game/${encodeURIComponent(boardId)}/move`,
      { method: 'POST', body: JSON.stringify({ move }) },
    ),

  gameResign: (sessionId: string, boardId: string) =>
    call<GameStateView>(
      `/api/coach/sessions/${encodeURIComponent(sessionId)}/game/${encodeURIComponent(boardId)}/resign`,
      { method: 'POST' },
    ),

  gameTakeback: (sessionId: string, boardId: string) =>
    call<GameStateView>(
      `/api/coach/sessions/${encodeURIComponent(sessionId)}/game/${encodeURIComponent(boardId)}/takeback`,
      { method: 'POST' },
    ),

  loadMessages: (sessionId: string) =>
    call<{ messages: Array<{ role: 'user' | 'assistant'; content: string; timestamp: number; source: string }> }>(
      `/api/coach/sessions/${encodeURIComponent(sessionId)}/messages`,
    ),
};
