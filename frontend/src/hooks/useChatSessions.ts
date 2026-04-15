/**
 * useChatSessions — Hook for managing chat sessions
 * Supports both legacy localStorage and PowerSync/TanStack DB live queries.
 * Controlled by LOCAL_FIRST_CHAT feature flag.
 */

import { useState, useEffect, useCallback, useMemo } from 'react';
import { useAuth } from '@clerk/nextjs';
import { LOCAL_FIRST_CHAT } from '@/lib/feature-flags';
import { usePowerSyncContext } from '@/lib/powersync/PowerSyncProvider';
import { useLiveQuery } from '@tanstack/react-db';
import { eq } from '@tanstack/db';

const STORAGE_KEY = 'chess-chat-sessions';

// Chat message interface compatible with existing ChatMessage from useChesster
export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant';
  content: string;
  fen?: string;
  timestamp: Date;
  maxTokens?: number;
  provider?: string;
  model?: string;
  response_time_ms?: number;
}

// Chat session interface
export interface ChatSession {
  id: string;
  title: string;
  messages: ChatMessage[];
  createdAt: number;
  updatedAt: number;
  isActive: boolean;
  currentFen: string;
  currentPgn?: string;
}

// Function to generate automatic chat titles based on chess position analysis
export const generateChatTitle = (messages: ChatMessage[], sessionFen?: string): string => {
  const userMessages = messages.filter(msg => msg.role === 'user');
  if (userMessages.length === 0) return 'New Chess Chat';

  const allUserContent = userMessages.map(msg => msg.content.toLowerCase()).join(' ');

  if (allUserContent.includes('sicilian')) {
    if (allUserContent.includes('alapin')) return 'Sicilian Alapin';
    if (allUserContent.includes('dragon')) return 'Sicilian Dragon';
    if (allUserContent.includes('najdorf')) return 'Sicilian Najdorf';
    return 'Sicilian Defense';
  }

  if (allUserContent.includes('caro-kann') || allUserContent.includes('caro kann')) return 'Caro-Kann Defense';
  if (allUserContent.includes('french')) return 'French Defense';
  if (allUserContent.includes('petrov') || allUserContent.includes('russian game')) return 'Petrov Defense';
  if (allUserContent.includes('king\'s indian') || allUserContent.includes('kings indian')) return 'King\'s Indian Defense';

  if (allUserContent.includes('queen\'s gambit') || allUserContent.includes('queens gambit')) {
    if (allUserContent.includes('declined')) return 'Queen\'s Gambit Declined';
    if (allUserContent.includes('accepted')) return 'Queen\'s Gambit Accepted';
    return 'Queen\'s Gambit';
  }

  if (allUserContent.includes('ruy lopez')) return 'Ruy Lopez';
  if (allUserContent.includes('italian')) return 'Italian Game';
  if (allUserContent.includes('london')) return 'London System';
  if (allUserContent.includes('catalan')) return 'Catalan Opening';
  if (allUserContent.includes('nimzo')) return 'Nimzo-Indian Defense';
  if (allUserContent.includes('english')) return 'English Opening';

  if (allUserContent.includes('fork')) return 'Tactical Forks';
  if (allUserContent.includes('pin')) return 'Tactical Pins';
  if (allUserContent.includes('skewer')) return 'Skewer Tactics';
  if (allUserContent.includes('sacrifice')) return 'Sacrificial Play';
  if (allUserContent.includes('checkmate')) return 'Checkmate Patterns';

  if (allUserContent.includes('endgame')) {
    if (allUserContent.includes('king and pawn')) return 'King & Pawn Endgame';
    if (allUserContent.includes('rook')) return 'Rook Endgame';
    return 'Endgame Study';
  }

  if (allUserContent.includes('strategy')) return 'Chess Strategy';
  if (allUserContent.includes('position') && allUserContent.includes('evaluation')) return 'Position Evaluation';
  if (allUserContent.includes('analysis')) return 'Position Analysis';

  const firstMessage = userMessages[0].content;
  const words = firstMessage.split(' ')
    .filter(word => word.length > 2)
    .slice(0, 3);

  if (words.length === 0) return 'Chess Discussion';

  return words.map((word: string) => word.charAt(0).toUpperCase() + word.slice(1)).join(' ');
};

const DEFAULT_FEN = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

// ─── Row ↔ ChatSession converters ───────

function rowToSession(row: Record<string, unknown>): ChatSession {
  let messages: ChatMessage[] = [];
  if (typeof row.messages === 'string') {
    try {
      messages = JSON.parse(row.messages as string).map((m: any) => ({
        ...m,
        timestamp: new Date(m.timestamp),
      }));
    } catch { messages = []; }
  }

  return {
    id: row.id as string,
    title: (row.title as string) ?? 'New Chat',
    messages,
    createdAt: row.created_at ? new Date(row.created_at as string).getTime() : Date.now(),
    updatedAt: row.updated_at ? new Date(row.updated_at as string).getTime() : Date.now(),
    isActive: row.is_active === 1 || row.is_active === true,
    currentFen: (row.current_fen as string) ?? DEFAULT_FEN,
    currentPgn: (row.current_pgn as string) ?? undefined,
  };
}

// ─── PowerSync-backed hook ──────────────

function useChatSessionsPowerSync() {
  const { userId } = useAuth();
  const { collections, isReady, database } = usePowerSyncContext();
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  const { data: rawData } = useLiveQuery(
    (q) => {
      if (!collections || !isReady || !userId) return null;
      return q
        .from({ c: collections.chatSessions })
        .where(({ c }) => eq(c.user_id, userId))
        .select(({ c }) => ({
          id: c.id,
          title: c.title,
          messages: c.messages,
          is_active: c.is_active,
          current_fen: c.current_fen,
          current_pgn: c.current_pgn,
          created_at: c.created_at,
          updated_at: c.updated_at,
        }));
    },
    [collections, isReady, userId],
  );

  const sessions = useMemo(
    () => (rawData ?? []).map(rowToSession).sort((a, b) => b.updatedAt - a.updatedAt),
    [rawData],
  );

  // Auto-select most recent session
  useEffect(() => {
    if (sessions.length > 0 && !currentSessionId) {
      setCurrentSessionId(sessions[0].id);
    }
  }, [sessions, currentSessionId]);

  const currentSession = useMemo(
    () => sessions.find(s => s.id === currentSessionId) ?? null,
    [sessions, currentSessionId],
  );

  const generateSessionId = useCallback(() => {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }, []);

  const hasChessContent = useCallback((content: string): boolean => {
    const lowerContent = content.toLowerCase();
    const chessKeywords = [
      'sicilian', 'french', 'caro-kann', 'scandinavian', 'alekhine', 'petrov', 'ruy lopez',
      'italian', 'english', 'london', 'catalan', 'nimzo', 'king\'s indian',
      'queen\'s gambit', 'opening', 'defense', 'gambit', 'endgame', 'middlegame',
      'tactics', 'strategy', 'position', 'fen', 'pgn', 'checkmate', 'fork', 'pin',
      'skewer', 'sacrifice', 'analysis', 'engine', 'stockfish', 'pawn', 'knight',
      'bishop', 'rook', 'queen', 'king', 'chess', 'move', 'play'
    ];
    return chessKeywords.some(keyword => lowerContent.includes(keyword));
  }, []);

  const createNewSession = useCallback((initialFen?: string) => {
    if (!database || !userId) return '';
    const id = generateSessionId();
    const now = new Date().toISOString();

    database.execute(
      `INSERT INTO chat_sessions (id, user_id, title, messages, is_active, current_fen, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
      [id, userId, 'New Chat', '[]', 1, initialFen || DEFAULT_FEN, now, now],
    );

    setCurrentSessionId(id);
    return id;
  }, [database, userId, generateSessionId]);

  const addMessageToSession = useCallback((message: ChatMessage, currentFen?: string) => {
    if (!database || !userId) return;

    const msgWithDefaults = {
      ...message,
      id: message.id || `${Date.now()}`,
      timestamp: new Date(),
    };

    if (!currentSessionId) {
      // Create new session with the message
      const id = generateSessionId();
      const now = new Date().toISOString();
      const msgs = [msgWithDefaults];
      const title = generateChatTitle(msgs, currentFen);

      database.execute(
        `INSERT INTO chat_sessions (id, user_id, title, messages, is_active, current_fen, created_at, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)`,
        [id, userId, title, JSON.stringify(msgs), 1, currentFen || DEFAULT_FEN, now, now],
      );

      setCurrentSessionId(id);
    } else {
      const session = sessions.find(s => s.id === currentSessionId);
      if (!session) return;

      const updatedMessages = [...session.messages, msgWithDefaults];
      const now = new Date().toISOString();

      let title = session.title;
      if (
        (session.title === 'New Chat' && message.role === 'user') ||
        (message.role === 'user' && session.messages.length <= 5 && hasChessContent(message.content))
      ) {
        title = generateChatTitle(updatedMessages, currentFen);
      }

      database.execute(
        `UPDATE chat_sessions SET messages = ?, title = ?, current_fen = ?, updated_at = ? WHERE id = ?`,
        [
          JSON.stringify(updatedMessages),
          title,
          currentFen || session.currentFen,
          now,
          currentSessionId,
        ],
      );
    }
  }, [currentSessionId, sessions, database, userId, generateSessionId, hasChessContent]);

  const switchToSession = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId);
  }, []);

  const deleteSession = useCallback((sessionId: string) => {
    if (!database) return;
    database.execute('DELETE FROM chat_sessions WHERE id = ?', [sessionId]);

    if (sessionId === currentSessionId) {
      const remaining = sessions.filter(s => s.id !== sessionId);
      setCurrentSessionId(remaining.length > 0 ? remaining[0].id : null);
    }
  }, [database, currentSessionId, sessions]);

  const renameSession = useCallback((sessionId: string, newTitle: string) => {
    if (!database) return;
    database.execute(
      'UPDATE chat_sessions SET title = ?, updated_at = ? WHERE id = ?',
      [newTitle, new Date().toISOString(), sessionId],
    );
  }, [database]);

  const clearCurrentSession = useCallback(() => {
    if (!database || !currentSessionId) return;
    database.execute(
      `UPDATE chat_sessions SET messages = '[]', title = 'New Chat', updated_at = ? WHERE id = ?`,
      [new Date().toISOString(), currentSessionId],
    );
  }, [database, currentSessionId]);

  const updateSessionMessages = useCallback((sessionId: string, messages: ChatMessage[]) => {
    if (!database) return;
    database.execute(
      'UPDATE chat_sessions SET messages = ?, updated_at = ? WHERE id = ?',
      [JSON.stringify(messages), new Date().toISOString(), sessionId],
    );
  }, [database]);

  const updateSessionFen = useCallback((fen: string) => {
    if (!database || !currentSessionId) return;
    database.execute(
      'UPDATE chat_sessions SET current_fen = ?, updated_at = ? WHERE id = ?',
      [fen, new Date().toISOString(), currentSessionId],
    );
  }, [database, currentSessionId]);

  const updateSessionPgn = useCallback((pgn: string) => {
    if (!database || !currentSessionId) return;
    database.execute(
      'UPDATE chat_sessions SET current_pgn = ?, updated_at = ? WHERE id = ?',
      [pgn, new Date().toISOString(), currentSessionId],
    );
  }, [database, currentSessionId]);

  return {
    sessions,
    currentSessionId,
    currentSession,
    createNewSession,
    addMessageToSession,
    switchToSession,
    deleteSession,
    renameSession,
    clearCurrentSession,
    updateSessionMessages,
    updateSessionFen,
    updateSessionPgn,
  };
}

// ─── Legacy localStorage-backed hook ────

function useChatSessionsLegacy() {
  const [sessions, setSessions] = useState<ChatSession[]>([]);
  const [currentSessionId, setCurrentSessionId] = useState<string | null>(null);

  useEffect(() => {
    const stored = localStorage.getItem(STORAGE_KEY);
    if (stored) {
      try {
        const parsedSessions: ChatSession[] = JSON.parse(stored);
        const migratedSessions = parsedSessions.map(session => ({
          ...session,
          currentFen: session.currentFen || DEFAULT_FEN,
          messages: session.messages.map(msg => ({
            ...msg,
            timestamp: new Date(msg.timestamp)
          }))
        }));

        setSessions(migratedSessions);
        if (migratedSessions.length > 0 && !currentSessionId) {
          const mostRecent = migratedSessions.sort((a, b) => b.updatedAt - a.updatedAt)[0];
          setCurrentSessionId(mostRecent.id);
        }
      } catch (error) {
        console.error('Failed to load chat sessions:', error);
      }
    }
  }, []);

  useEffect(() => {
    if (sessions.length > 0) {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(sessions));
    }
  }, [sessions]);

  const generateSessionId = useCallback(() => {
    return `session_${Date.now()}_${Math.random().toString(36).substr(2, 9)}`;
  }, []);

  const createNewSession = useCallback((initialFen?: string) => {
    const newSession: ChatSession = {
      id: generateSessionId(),
      title: 'New Chat',
      messages: [],
      createdAt: Date.now(),
      updatedAt: Date.now(),
      isActive: true,
      currentFen: initialFen || DEFAULT_FEN,
    };

    setSessions(prev => [newSession, ...prev]);
    setCurrentSessionId(newSession.id);
    return newSession.id;
  }, [generateSessionId]);

  const currentSession = useMemo(() => {
    return sessions.find(session => session.id === currentSessionId) || null;
  }, [sessions, currentSessionId]);

  const hasChessContent = useCallback((content: string): boolean => {
    const lowerContent = content.toLowerCase();
    const chessKeywords = [
      'sicilian', 'french', 'caro-kann', 'scandinavian', 'alekhine', 'petrov', 'ruy lopez',
      'italian', 'english', 'london', 'catalan', 'nimzo', 'king\'s indian',
      'queen\'s gambit', 'opening', 'defense', 'gambit', 'endgame', 'middlegame',
      'tactics', 'strategy', 'position', 'fen', 'pgn', 'checkmate', 'fork', 'pin',
      'skewer', 'sacrifice', 'analysis', 'engine', 'stockfish', 'pawn', 'knight',
      'bishop', 'rook', 'queen', 'king', 'chess', 'move', 'play'
    ];
    return chessKeywords.some(keyword => lowerContent.includes(keyword));
  }, []);

  const addMessageToSession = useCallback((message: ChatMessage, currentFen?: string) => {
    if (!currentSessionId) {
      const newSessionId = generateSessionId();
      const newSession: ChatSession = {
        id: newSessionId,
        title: 'New Chat',
        messages: [{ ...message, id: message.id || `${Date.now()}`, timestamp: new Date() }],
        createdAt: Date.now(),
        updatedAt: Date.now(),
        isActive: true,
        currentFen: currentFen || DEFAULT_FEN,
      };
      newSession.title = generateChatTitle(newSession.messages, currentFen);
      setSessions(prev => [newSession, ...prev]);
      setCurrentSessionId(newSessionId);
    } else {
      setSessions(prev =>
        prev.map(session =>
          session.id === currentSessionId
            ? {
                ...session,
                messages: [...session.messages, { ...message, id: message.id || `${Date.now()}`, timestamp: new Date() }],
                updatedAt: Date.now(),
                title: (session.title === 'New Chat' && message.role === 'user') ||
                       (message.role === 'user' && session.messages.length <= 5 && hasChessContent(message.content))
                  ? generateChatTitle([...session.messages, message], currentFen)
                  : session.title,
                currentFen: currentFen || session.currentFen
              }
            : session
        )
      );
    }
  }, [currentSessionId, generateSessionId, hasChessContent]);

  const switchToSession = useCallback((sessionId: string) => {
    setCurrentSessionId(sessionId);
  }, []);

  const deleteSession = useCallback((sessionId: string) => {
    setSessions(prev => {
      const filtered = prev.filter(session => session.id !== sessionId);
      if (sessionId === currentSessionId) {
        if (filtered.length > 0) {
          const mostRecent = filtered.sort((a, b) => b.updatedAt - a.updatedAt)[0];
          setCurrentSessionId(mostRecent.id);
        } else {
          setCurrentSessionId(null);
        }
      }
      return filtered;
    });
  }, [currentSessionId]);

  const renameSession = useCallback((sessionId: string, newTitle: string) => {
    setSessions(prev =>
      prev.map(session =>
        session.id === sessionId
          ? { ...session, title: newTitle, updatedAt: Date.now() }
          : session
      )
    );
  }, []);

  const clearCurrentSession = useCallback(() => {
    if (currentSessionId) {
      setSessions(prev =>
        prev.map(session =>
          session.id === currentSessionId
            ? { ...session, messages: [], updatedAt: Date.now(), title: 'New Chat' }
            : session
        )
      );
    }
  }, [currentSessionId]);

  const updateSessionMessages = useCallback((sessionId: string, messages: ChatMessage[]) => {
    setSessions(prev =>
      prev.map(session =>
        session.id === sessionId
          ? { ...session, messages, updatedAt: Date.now() }
          : session
      )
    );
  }, []);

  const updateSessionFen = useCallback((fen: string) => {
    if (currentSessionId) {
      setSessions(prev =>
        prev.map(session =>
          session.id === currentSessionId
            ? { ...session, currentFen: fen, updatedAt: Date.now() }
            : session
        )
      );
    }
  }, [currentSessionId]);

  const updateSessionPgn = useCallback((pgn: string) => {
    if (currentSessionId) {
      setSessions(prev =>
        prev.map(session =>
          session.id === currentSessionId
            ? { ...session, currentPgn: pgn, updatedAt: Date.now() }
            : session
        )
      );
    }
  }, [currentSessionId]);

  return {
    sessions,
    currentSessionId,
    currentSession,
    createNewSession,
    addMessageToSession,
    switchToSession,
    deleteSession,
    renameSession,
    clearCurrentSession,
    updateSessionMessages,
    updateSessionFen,
    updateSessionPgn,
  };
}

// ─── Exported hook ──────────────────────

export const useChatSessions = () => {
  // PowerSync path disabled: @tanstack/react-db useLiveQuery lacks
  // getServerSnapshot for SSR, causing HTTP 500. Re-enable when fixed.
  return useChatSessionsLegacy();
};
