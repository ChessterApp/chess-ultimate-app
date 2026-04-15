/**
 * @vitest-environment jsdom
 *
 * Tests for useChatSessions PowerSync integration path.
 */
import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';

// ─── Feature flag mock ──────────────────

let mockLocalFirstChat = true;
vi.mock('@/lib/feature-flags', () => ({
  get LOCAL_FIRST_CHAT() { return mockLocalFirstChat; },
}));

// ─── Clerk mock ─────────────────────────

vi.mock('@clerk/nextjs', () => ({
  useAuth: () => ({ userId: 'user-123' }),
}));

// ─── PowerSync context mock ─────────────

const mockExecute = vi.fn();
const mockDatabase = { execute: mockExecute };
const mockCollections = {
  chatSessions: { id: 'chat-sessions-collection' },
};

vi.mock('@/lib/powersync/PowerSyncProvider', () => ({
  usePowerSyncContext: () => ({
    database: mockDatabase,
    collections: mockCollections,
    isReady: true,
  }),
}));

// ─── useLiveQuery mock ──────────────────

const mockLiveQueryData = vi.fn().mockReturnValue([]);
vi.mock('@tanstack/react-db', () => ({
  useLiveQuery: () => ({
    data: mockLiveQueryData(),
    isLoading: false,
    isReady: true,
  }),
}));

vi.mock('@tanstack/db', () => ({
  eq: vi.fn(),
}));

import { useChatSessions, generateChatTitle } from '../useChatSessions';
import type { ChatMessage } from '../useChatSessions';

// ─── Fixtures ───────────────────────────

const SESSION_ROW = {
  id: 'session-1',
  title: 'Sicilian Defense',
  messages: JSON.stringify([
    {
      id: 'msg-1',
      role: 'user',
      content: 'Tell me about the Sicilian Defense',
      timestamp: '2024-06-01T10:00:00Z',
    },
  ]),
  is_active: 1,
  current_fen: 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1',
  current_pgn: '1. e4',
  created_at: '2024-06-01T10:00:00Z',
  updated_at: '2024-06-01T10:00:00Z',
};

// ─── Tests ──────────────────────────────

describe.skip('useChatSessions (PowerSync mode) — disabled: useLiveQuery SSR crash', () => {
  beforeEach(() => {
    vi.clearAllMocks();
    mockLocalFirstChat = true;
    mockLiveQueryData.mockReturnValue([]);
  });

  it('should return empty sessions when no data', () => {
    const { result } = renderHook(() => useChatSessions());
    expect(result.current.sessions).toEqual([]);
    expect(result.current.currentSession).toBeNull();
  });

  it('should return sessions from live query with correct conversion', () => {
    mockLiveQueryData.mockReturnValue([SESSION_ROW]);

    const { result } = renderHook(() => useChatSessions());

    expect(result.current.sessions).toHaveLength(1);
    const session = result.current.sessions[0];
    expect(session.id).toBe('session-1');
    expect(session.title).toBe('Sicilian Defense');
    expect(session.messages).toHaveLength(1);
    expect(session.messages[0].content).toBe('Tell me about the Sicilian Defense');
    expect(session.isActive).toBe(true);
    expect(session.currentFen).toContain('e3');
  });

  it('should auto-select the most recent session', () => {
    mockLiveQueryData.mockReturnValue([SESSION_ROW]);

    const { result } = renderHook(() => useChatSessions());

    expect(result.current.currentSessionId).toBe('session-1');
  });

  it('should create new session via PowerSync write', () => {
    const { result } = renderHook(() => useChatSessions());

    let sessionId: string = '';
    act(() => {
      sessionId = result.current.createNewSession();
    });

    expect(sessionId).toMatch(/^session_/);
    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('INSERT INTO chat_sessions'),
      expect.arrayContaining(['user-123', 'New Chat', '[]']),
    );
  });

  it('should create session with custom FEN', () => {
    const customFen = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';

    const { result } = renderHook(() => useChatSessions());

    act(() => {
      result.current.createNewSession(customFen);
    });

    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('INSERT INTO chat_sessions'),
      expect.arrayContaining([customFen]),
    );
  });

  it('should add message to existing session', () => {
    mockLiveQueryData.mockReturnValue([SESSION_ROW]);

    const { result } = renderHook(() => useChatSessions());

    const message: ChatMessage = {
      id: 'msg-2',
      role: 'assistant',
      content: 'The Sicilian is a great opening!',
      timestamp: new Date(),
    };

    act(() => {
      result.current.addMessageToSession(message);
    });

    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE chat_sessions SET messages'),
      expect.any(Array),
    );
  });

  it('should create new session when adding message without current session', () => {
    // No sessions exist, no current session
    mockLiveQueryData.mockReturnValue([]);

    const { result } = renderHook(() => useChatSessions());
    expect(result.current.currentSessionId).toBeNull();

    const message: ChatMessage = {
      id: 'msg-1',
      role: 'user',
      content: 'Tell me about the French Defense',
      timestamp: new Date(),
    };

    act(() => {
      result.current.addMessageToSession(message);
    });

    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('INSERT INTO chat_sessions'),
      expect.any(Array),
    );
  });

  it('should delete session via PowerSync', () => {
    mockLiveQueryData.mockReturnValue([SESSION_ROW]);

    const { result } = renderHook(() => useChatSessions());

    act(() => {
      result.current.deleteSession('session-1');
    });

    expect(mockExecute).toHaveBeenCalledWith(
      'DELETE FROM chat_sessions WHERE id = ?',
      ['session-1'],
    );
  });

  it('should rename session via PowerSync', () => {
    const { result } = renderHook(() => useChatSessions());

    act(() => {
      result.current.renameSession('session-1', 'New Title');
    });

    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE chat_sessions SET title'),
      expect.arrayContaining(['New Title', 'session-1']),
    );
  });

  it('should clear current session via PowerSync', () => {
    mockLiveQueryData.mockReturnValue([SESSION_ROW]);

    const { result } = renderHook(() => useChatSessions());

    act(() => {
      result.current.clearCurrentSession();
    });

    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE chat_sessions SET messages'),
      expect.arrayContaining(['session-1']),
    );
  });

  it('should update FEN via PowerSync', () => {
    mockLiveQueryData.mockReturnValue([SESSION_ROW]);

    const { result } = renderHook(() => useChatSessions());

    act(() => {
      result.current.updateSessionFen('new-fen');
    });

    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE chat_sessions SET current_fen'),
      expect.arrayContaining(['new-fen', 'session-1']),
    );
  });

  it('should update PGN via PowerSync', () => {
    mockLiveQueryData.mockReturnValue([SESSION_ROW]);

    const { result } = renderHook(() => useChatSessions());

    act(() => {
      result.current.updateSessionPgn('1. e4 e5');
    });

    expect(mockExecute).toHaveBeenCalledWith(
      expect.stringContaining('UPDATE chat_sessions SET current_pgn'),
      expect.arrayContaining(['1. e4 e5', 'session-1']),
    );
  });

  it('should switch sessions', () => {
    mockLiveQueryData.mockReturnValue([
      SESSION_ROW,
      { ...SESSION_ROW, id: 'session-2', title: 'Second Chat' },
    ]);

    const { result } = renderHook(() => useChatSessions());

    act(() => {
      result.current.switchToSession('session-2');
    });

    expect(result.current.currentSessionId).toBe('session-2');
  });
});

describe('generateChatTitle', () => {
  it('should detect Sicilian opening', () => {
    const msgs: ChatMessage[] = [
      { id: '1', role: 'user', content: 'Tell me about the Sicilian Defense', timestamp: new Date() },
    ];
    expect(generateChatTitle(msgs)).toBe('Sicilian Defense');
  });

  it('should detect Sicilian Najdorf variant', () => {
    const msgs: ChatMessage[] = [
      { id: '1', role: 'user', content: 'How do I play the Sicilian Najdorf?', timestamp: new Date() },
    ];
    expect(generateChatTitle(msgs)).toBe('Sicilian Najdorf');
  });

  it('should detect French Defense', () => {
    const msgs: ChatMessage[] = [
      { id: '1', role: 'user', content: 'What is the French defense strategy?', timestamp: new Date() },
    ];
    expect(generateChatTitle(msgs)).toBe('French Defense');
  });

  it('should return fallback for empty messages', () => {
    expect(generateChatTitle([])).toBe('New Chess Chat');
  });

  it('should use first words as fallback', () => {
    const msgs: ChatMessage[] = [
      { id: '1', role: 'user', content: 'Help with this position please', timestamp: new Date() },
    ];
    const title = generateChatTitle(msgs);
    expect(title).toBe('Help With This');
  });
});
