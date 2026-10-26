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
  /** Lines taken back and kept in the notation: the moves after `at_ply` plies of the main line (26.10). */
  variations?: Array<{ at_ply: number; moves: string[] }>;
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

/** Hermes's 404 for a session that doesn't exist or isn't the caller's. */
export const SESSION_NOT_FOUND = 'session_not_found' as const;

/**
 * Like `call`, but reports Hermes's own "Session not found" 404 as
 * SESSION_NOT_FOUND. Any other failure — a 404 from a Hermes without the
 * route, a 5xx, a network error — is still `null`, so callers can forget a
 * dead session id without forgetting a live one on a hiccup.
 */
async function callOrSessionNotFound<T>(path: string): Promise<T | typeof SESSION_NOT_FOUND | null> {
  try {
    const res = await fetch(path, {
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
    });
    if (!res.ok) {
      if (await handleRestrictedResponse(res)) return null;
      if (res.status === 404) {
        try {
          // The proxy wraps Hermes's body: { error, detail: { detail } }.
          const data = (await res.json()) as { detail?: { detail?: unknown } };
          if (data.detail?.detail === 'Session not found') return SESSION_NOT_FOUND;
        } catch {
          // not JSON — treat as a plain failure
        }
      }
      return null;
    }
    return (await res.json()) as T;
  } catch {
    return null;
  }
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
    callOrSessionNotFound<{ active_board_id: string | null; boards: BoardRecord[] }>(
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

  /** The game goes on from the position after `ply` plies of its own record: the later moves are undone (26.10). */
  gameContinue: (sessionId: string, boardId: string, ply: number) =>
    callWithError<GameStateView>(
      `/api/coach/sessions/${encodeURIComponent(sessionId)}/game/${encodeURIComponent(boardId)}/continue`,
      { method: 'POST', body: JSON.stringify({ ply }) },
    ),

  loadMessages: (sessionId: string) =>
    call<{ messages: Array<{ role: 'user' | 'assistant'; content: string; timestamp: number; source: string }> }>(
      `/api/coach/sessions/${encodeURIComponent(sessionId)}/messages`,
    ),

  /**
   * Have Hermes analyse `fen` now, fire-and-forget: the analysis lands in its
   * cache and a question about the position starts from Stockfish's result
   * instead of waiting ~1.7 s for it. Plain fetch, not `call` — a background
   * request must never redirect the student, and any failure (an older Hermes
   * answers 404) just means no head start.
   */
  prewarmEngine: (fen: string) => {
    void fetch('/api/coach/voice/engine-note', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ fen }),
    }).catch(() => undefined);
  },
};
