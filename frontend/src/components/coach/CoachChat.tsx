'use client';

import React, {
  useState,
  useRef,
  useCallback,
  useEffect,
  useLayoutEffect,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { useTranslations } from 'next-intl';
import { Chess } from 'chess.js';
import { russianToSan } from '@/lib/russianNotation';
import useGeminiLive from '@/hooks/useGeminiLive';
import type { CoachMessage, BoardAction, GameResult } from '@/types/coach';
import { coachApi, type GameStateView } from '@/lib/coach/boards-api';
import { handleRestrictedResponse } from '@/lib/access-fetch';
import { fitTextarea, isNearBottom, shouldSendOnEnter } from './chat-dom';
import Composer from './Composer';
import type { AttachKind } from './AttachSheet';
import MessageList, { ChipRow, PeekMessage, useStarterPrompts } from './MessageList';
import { applyStreamFrame } from '@/lib/coach/message-stream';
import { contextChips } from '@/lib/coach/context-chips';
import type { CoachMode } from '@/lib/coach/coach-mode';
import type { ReviewMomentsSummary } from '@/lib/coach/tool-summary';

/** «ход чёрных», "black to move", «қаралардың жүрісі» → 'b' (and White likewise); else null. */
export function sideToMoveCommand(text: string): 'w' | 'b' | null {
  const t = text.trim().toLowerCase().replace(/ё/g, 'е').replace(/[.!]+$/, '');
  if (/^(?:теперь\s+|сейчас\s+|нет,?\s+)?(?:ход\s+черных|черные\s+ходят|ходят\s+черные|за\s+черных)$|^(?:it'?s\s+)?black\s+to\s+(?:move|play)$|^black'?s\s+(?:move|turn)$|^қаралар(?:дың)?\s+жүрісі$/.test(t)) return 'b';
  if (/^(?:теперь\s+|сейчас\s+|нет,?\s+)?(?:ход\s+белых|белые\s+ходят|ходят\s+белые|за\s+белых)$|^(?:it'?s\s+)?white\s+to\s+(?:move|play)$|^white'?s\s+(?:move|turn)$|^ақтар(?:дың)?\s+жүрісі$/.test(t)) return 'w';
  return null;
}

/** The same position with *side* to move, or null when that is not a legal position. */
export function withSideToMove(fen: string, side: 'w' | 'b'): string | null {
  const parts = fen.trim().split(/\s+/);
  if (parts.length < 2) return null;
  parts[1] = side;
  if (parts.length >= 4) parts[3] = '-'; // no en passant after a switch
  const next = parts.join(' ');
  try {
    const chess = new Chess(next);
    // The side that just moved may not stand in check (chess.js does not refuse it).
    const other = side === 'w' ? 'b' : 'w';
    for (const row of chess.board()) {
      for (const sq of row) {
        if (sq && sq.type === 'k' && sq.color === other && chess.isAttacked(sq.square, side)) return null;
      }
    }
    return next;
  } catch {
    return null;
  }
}

interface CoachChatProps {
  currentFen: string;
  /** The moves on the board, when a game is loaded (a review by voice uses them). */
  currentPgn?: string;
  sessionId: string | null;
  /** The board (tab) the student is looking at; sent as board_id on every turn. */
  boardId?: string | null;
  /** Restore the session's message history from the server on mount / session switch. */
  restoreHistory?: boolean;
  onBoardActions: (actions: BoardAction[]) => void;
  onSessionCreated?: (id: string) => void;
  /** The server's active board after a turn (the coach may have opened one). */
  onActiveBoardChanged?: (boardId: string) => void;
  onOpenGame?: (game: GameResult) => void;
  /**
   * Optional grounding preamble prepended to the OUTGOING message sent to the
   * coach — never shown in the user's chat bubble. The Review Coach Drawer uses
   * this to scope every question to the move currently under review.
   */
  contextNote?: string;
  /** The game against the coach on the board, if any — the voice coach hears its moves (src/lib/coach/voice-game.ts). */
  game?: GameStateView | null;
  /** Hide the composer (a game's action bar stands in for it); voice controls stay while voice is on. */
  composerHidden?: boolean;
  /** A finished assistant answer or remark — the play strip quotes it in the coach's bubble. */
  onAssistantReply?: (text: string) => void;
  /**
   * 'peek' (the mobile sheet's low detent): the coach's latest line, one row of
   * chips and the composer; 'thread' (default): the whole conversation.
   */
  view?: 'thread' | 'peek';
  /** The peek's line was tapped: the host opens the history. */
  onExpand?: () => void;
  /** The composer got focus (the mobile sheet makes room for the keyboard). */
  onComposerFocus?: () => void;
  /** Shown above the composer: the game's action bar, the puzzle's steps. In peek it replaces the line and chips. */
  footer?: React.ReactNode;
  /** What the board is doing — the contextual chips follow it. */
  mode?: CoachMode;
  /** Bring the board into view after a card put something on it (phones: the sheet drops to peek). */
  onShowBoard?: () => void;
  /** «Начать» on a game review card: the host replays its moments on the board. */
  onStartMoments?: (review: ReviewMomentsSummary) => void;
}

/** Imperative handle so a host (e.g. the Review Coach Drawer) can send a
 * message programmatically — used by the drawer's one-tap starter chips. */
export interface CoachChatHandle {
  send: (text: string) => void;
  /**
   * Show an assistant message streamed from elsewhere (a game comment): POSTs
   * `url` with `body`, reads `delta` SSE frames into one assistant bubble.
   */
  streamAssistant: (url: string, body: Record<string, unknown>) => Promise<void>;
  /** Open the composer's attach sheet (paste / upload / photo / link). */
  openAttach: () => void;
}

/** A pasted text that is a whole game in PGN (move numbers + SAN), not a question. */
const PGN_RE = /(?:^|\s)1\.\s*[a-hNBRQKO0]/;
const FEN_RE = /^\s*([rnbqkpRNBQKP1-8]+\/){7}[rnbqkpRNBQKP1-8]+\s+[wb]\s+(-|[KQkq]{1,4})\s+(-|[a-h][36])(\s+\d+\s+\d+)?\s*$/;

/** A link to one game on Lichess (8-char id) or Chess.com (numeric game id). */
const GAME_URL_RE =
  /^(?:https?:\/\/)?(?:www\.)?(?:lichess\.org\/(?:game\/export\/)?[A-Za-z0-9]{8}(?:[A-Za-z0-9]{4})?(?:[/#?].*)?|chess\.com\/(?:(?:analysis\/)?game\/(?:live|daily|computer)\/\d+|live\/game\/\d+)(?:[/#?].*)?)$/i;

/**
 * Russian notation → SAN: students paste "1.e4 e5 2.Фh5 Кc6 3.Сc4" or "1.е4 е5 2.Кф3 Кс6"
 * (Кр — king, Ф — queen, Л — rook, С — bishop, К — knight; Cyrillic and transliterated files;
 * х/×/: as the capture sign; 0-0 for castling). The board's parser knows only SAN and silently
 * dropped such a game while the chat said it was loaded (2026-09-29); Cyrillic files were not read
 * until 2026-10-08.
 */
export function normalizeRussianSan(text: string): string {
  return russianToSan(text || '');
}

/** True when the board's parser (chess.js) reads *pgn* as a game. */
function isReadablePgn(pgn: string): boolean {
  try {
    new Chess().loadPgn(pgn);
    return true;
  } catch {
    return false;
  }
}

export function classifyPastedText(text: string): 'pgn' | 'fen' | 'url' | null {
  const t = normalizeRussianSan((text || '').trim());
  if (!t) return null;
  if (FEN_RE.test(t)) return 'fen';
  if (GAME_URL_RE.test(t)) return 'url';
  if (t.length > 20 && PGN_RE.test(t) && (t.match(/\d+\./g) ?? []).length >= 2) return 'pgn';
  return null;
}

/** The voice coach's words without the tags of the page's notes to it ([Idea], [Check], …). */
export function stripVoiceNoteTags(text: string): string {
  return text.replace(/\[(?:Idea|Check|Engine|Topic|Opening|Puzzle)\]\s*/gi, '');
}

/** Strip the `data:image/…;base64,` prefix — the conversion routes want raw base64. */
function dataUrlToBase64(dataUrl: string): string {
  const idx = dataUrl.indexOf(',');
  return idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl;
}

const CoachChat = forwardRef<CoachChatHandle, CoachChatProps>(function CoachChat(
  {
    currentFen,
    currentPgn,
    sessionId,
    boardId,
    restoreHistory = false,
    onBoardActions,
    onSessionCreated,
    onActiveBoardChanged,
    onOpenGame,
    contextNote,
    game = null,
    composerHidden = false,
    onAssistantReply,
    view = 'thread',
    onExpand,
    onComposerFocus,
    footer,
    mode = 'explore',
    onShowBoard,
    onStartMoments,
  },
  ref,
) {
  const t = useTranslations('coach');
  const onAssistantReplyRef = useRef(onAssistantReply);
  onAssistantReplyRef.current = onAssistantReply;
  const [messages, setMessages] = useState<CoachMessage[]>([]);

  // Restore the conversation when the page opens on a saved session or the
  // student switches sessions. Text and voice messages are both persisted
  // server-side; before this the history vanished on every reload.
  const restoredForRef = useRef<string | null>(null);
  useEffect(() => {
    if (!restoreHistory) return;
    if (!sessionId) {
      restoredForRef.current = null;
      stickRef.current = true;
      setMessages([]);
      return;
    }
    if (restoredForRef.current === sessionId) return;
    restoredForRef.current = sessionId;
    let cancelled = false;
    void (async () => {
      const data = await coachApi.loadMessages(sessionId);
      if (cancelled || !data) return;
      stickRef.current = true;
      setMessages(
        data.messages.map((m, i) => ({
          id: `restored-${sessionId}-${i}`,
          role: m.role,
          content: m.content,
          timestamp: new Date((m.timestamp || 0) * 1000),
        })),
      );
    })();
    return () => {
      cancelled = true;
    };
  }, [restoreHistory, sessionId]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [toolActive, setToolActive] = useState<string | null>(null);
  // Set when the monthly voice quota is exhausted, so we show the "minutes used
  // up — text is unlimited" message in place of a connection error.
  const [voiceQuotaExhausted, setVoiceQuotaExhausted] = useState(false);
  const scrollRef = useRef<HTMLDivElement>(null);
  const textareaRef = useRef<HTMLTextAreaElement>(null);
  // Follow the stream only while the student is at the bottom; once they
  // scroll up to read, leave them there and offer a jump-down pill instead.
  const stickRef = useRef(true);
  const [hasUnseen, setHasUnseen] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  // ── Voice mode (Gemini Live) ──────────────────────────────────────────────
  // Keep the latest FEN in a ref so the hook's getFen closure never goes stale.
  const currentFenRef = useRef(currentFen);
  currentFenRef.current = currentFen;
  const getFen = useCallback(() => currentFenRef.current, []);
  const currentPgnRef = useRef(currentPgn);
  currentPgnRef.current = currentPgn;
  const getPgn = useCallback(() => currentPgnRef.current, []);

  // Shared conversation memory: text and voice must use the SAME Hermes session
  // id. Track the active id in a ref so voice callbacks read it synchronously,
  // and keep it in sync as the sessionId prop catches up after creation.
  const activeSessionIdRef = useRef<string | null>(sessionId);
  useEffect(() => {
    if (sessionId) activeSessionIdRef.current = sessionId;
  }, [sessionId]);
  const getSessionId = useCallback(() => activeSessionIdRef.current, []);

  // Id of the in-progress voice transcript bubble per role, so streaming
  // (final:false) chunks update the same message and final:true freezes it.
  const voiceMsgIdRef = useRef<{ user: string | null; model: string | null }>({
    user: null,
    model: null,
  });
  // Full accumulated transcript text per role, so on final we persist the whole
  // utterance (not just the last streamed chunk) into the shared session.
  const voiceTextRef = useRef<{ user: string; model: string }>({
    user: '',
    model: '',
  });
  // Turn correlation id per in-progress utterance, captured on its first chunk,
  // so the persisted row joins to the voice coach_events for the same turn.
  const voiceTurnIdRef = useRef<{ user: string | null; model: string | null }>({
    user: null,
    model: null,
  });

  const handleTranscript = useCallback(
    (tr: {
      role: 'user' | 'model';
      text: string;
      final: boolean;
      turnId?: string;
    }) => {
      const mappedRole: 'user' | 'assistant' =
        tr.role === 'user' ? 'user' : 'assistant';
      const currentId = voiceMsgIdRef.current[tr.role];
      // An empty closing mark (the hook ends utterances at turn edges) with no
      // open bubble has nothing to finish.
      if (!tr.text && !currentId) return;
      // The coach's words without a system tag it read out («[Idea] Ход b3…» reached
      // the student's chat on production, 2026-10-07); the student's words as heard.
      const shown = (s: string) => (tr.role === 'model' ? stripVoiceNoteTags(s) : s);
      if (currentId) {
        voiceTextRef.current[tr.role] += tr.text;
        const content = shown(voiceTextRef.current[tr.role]);
        setMessages((prev) =>
          prev.map((m) =>
            m.id === currentId ? { ...m, content } : m
          )
        );
      } else {
        const id = crypto.randomUUID();
        voiceMsgIdRef.current[tr.role] = id;
        voiceTextRef.current[tr.role] = tr.text;
        // Capture the turn id at the start of the utterance so the whole message
        // persists under one correlation id even as chunks stream in.
        voiceTurnIdRef.current[tr.role] = tr.turnId ?? null;
        setMessages((prev) => [
          ...prev,
          { id, role: mappedRole, content: shown(tr.text), timestamp: new Date() },
        ]);
      }
      if (tr.final) {
        // Persist the finalized utterance into the shared Hermes session so the
        // text coach sees it too. Fire-and-forget: never disrupt the voice call.
        const fullText = shown(voiceTextRef.current[tr.role]).trim();
        const sid = activeSessionIdRef.current;
        if (sid && fullText) {
          fetch(`/api/coach/sessions/${encodeURIComponent(sid)}/messages`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
              role: mappedRole,
              content: fullText,
              source: 'voice',
              // Phase 2: true utterance time (not the write time) + turn id.
              client_ts: new Date().toISOString(),
              turn_id:
                voiceTurnIdRef.current[tr.role] ?? tr.turnId ?? undefined,
            }),
          }).catch((err) =>
            console.error('[coach] transcript write-back failed:', err)
          );
        }
        voiceMsgIdRef.current[tr.role] = null;
        voiceTextRef.current[tr.role] = '';
        voiceTurnIdRef.current[tr.role] = null;
      }
    },
    []
  );

  // Apply the result of a voice-driven tool call. Board actions flow through the
  // SAME handler the text agent uses (onBoardActions -> board state), so the
  // local FEN stays consistent for subsequent voice board-update pushes. Any
  // game-search results are surfaced through the existing game-list renderer.
  const handleVoiceToolResult = useCallback(
    (name: string, result: unknown) => {
      if (!result || typeof result !== 'object') return;
      const data = result as { board_actions?: BoardAction[]; result?: unknown };

      if (Array.isArray(data.board_actions) && data.board_actions.length > 0) {
        onBoardActions(data.board_actions);
      }

      const inner = data.result;
      if (
        Array.isArray(inner) &&
        inner.length > 0 &&
        inner[0] &&
        typeof inner[0] === 'object' &&
        'white_name' in (inner[0] as Record<string, unknown>)
      ) {
        const games = inner as unknown as GameResult[];
        setMessages((prev) => [
          ...prev,
          {
            id: crypto.randomUUID(),
            role: 'assistant',
            content: '',
            gameResults: games,
            timestamp: new Date(),
          },
        ]);
      }
    },
    [onBoardActions]
  );

  const handleVoiceQuotaExhausted = useCallback(() => {
    setVoiceQuotaExhausted(true);
  }, []);

  // The game against the coach, for the voice coach: read through a ref (the hook keeps its options in one).
  const gameRef = useRef<GameStateView | null>(game);
  gameRef.current = game;
  const getGame = useCallback(() => gameRef.current, []);

  const {
    status: voiceStatus,
    isSupported: voiceSupported,
    isActive: voiceActive,
    error: voiceError,
    prepare: voicePrepare,
    connect: voiceConnect,
    prefetch: voicePrefetch,
    disconnect: voiceDisconnect,
    sendBoardUpdate: voiceSendBoardUpdate,
    remainingSeconds: voiceRemainingSeconds,
  } = useGeminiLive({
    getFen,
    getPgn,
    getSessionId,
    onTranscript: handleTranscript,
    onToolResult: handleVoiceToolResult,
    onQuotaExhausted: handleVoiceQuotaExhausted,
    getGame,
  });

  // While voice mode is live, push every board change into the session so the
  // voice coach stays in sync (the connect-time token only carries the initial
  // FEN). Debounced to coalesce premoves/takebacks; skips the initial FEN since
  // the session already anchors it on open.
  const voicePrimedRef = useRef(false);
  useEffect(() => {
    if (!voiceActive) {
      voicePrimedRef.current = false;
      return;
    }
    if (!voicePrimedRef.current) {
      voicePrimedRef.current = true;
      return;
    }
    const handle = setTimeout(() => voiceSendBoardUpdate(currentFen), 300);
    return () => clearTimeout(handle);
  }, [currentFen, voiceActive, voiceSendBoardUpdate]);

  // Make sure a Hermes session exists before voice starts, so text and voice
  // share one conversation memory. Reuses the current session if present,
  // otherwise creates one and lifts it to the parent.
  const ensureVoiceSession = useCallback(async () => {
    if (activeSessionIdRef.current) return;
    try {
      const res = await fetch('/api/coach/sessions', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({}),
      });
      if (res.ok) {
        const data = await res.json();
        if (data?.id) {
          activeSessionIdRef.current = data.id;
          restoredForRef.current = data.id; // brand new — nothing to reload
          onSessionCreated?.(data.id);
        }
      }
    } catch (err) {
      console.error('[coach] failed to create voice session:', err);
    }
  }, [onSessionCreated]);

  const toggleVoice = useCallback(async () => {
    if (voiceActive) {
      voiceDisconnect();
      return;
    }
    // Fresh attempt — clear any prior "minutes used up" banner.
    setVoiceQuotaExhausted(false);
    // Grab the mic FIRST, inside this tap handler, before any network await.
    // On mobile Safari the user-activation window closes after a network round
    // trip, so acquiring the mic after ensureVoiceSession()/token fetch would
    // make getUserMedia reject. prepare() surfaces its own error on failure.
    try {
      await voicePrepare();
    } catch {
      return;
    }
    // The session and the token in parallel: a brand-new session has nothing
    // for the token's conversation recap, and the voice calls read the session
    // id only later (about 1 s saved on chesster.io when there was none).
    void ensureVoiceSession();
    voiceConnect();
  }, [voiceActive, voicePrepare, voiceConnect, voiceDisconnect, ensureVoiceSession]);

  // The session token takes 1.4-3 s to mint on chesster.io: ask for it while
  // the pointer is on the mic button, before the tap.
  const prefetchVoice = useCallback(() => {
    if (!voiceActive) voicePrefetch();
  }, [voiceActive, voicePrefetch]);

  // Disconnect a live session on unmount without re-running on every toggle.
  const voiceActiveRef = useRef(voiceActive);
  voiceActiveRef.current = voiceActive;
  useEffect(() => {
    return () => {
      if (voiceActiveRef.current) {
        voiceDisconnect();
      }
    };
  }, [voiceDisconnect]);

  const scrollToBottom = useCallback(() => {
    const el = scrollRef.current;
    if (el) el.scrollTop = el.scrollHeight;
    stickRef.current = true;
    setHasUnseen(false);
  }, []);

  const handleScroll = useCallback(() => {
    const el = scrollRef.current;
    if (!el) return;
    stickRef.current = isNearBottom(el);
    if (stickRef.current) setHasUnseen(false);
  }, []);

  useLayoutEffect(() => {
    if (stickRef.current) scrollToBottom();
    else setHasUnseen(true);
  }, [messages, scrollToBottom]);

  useLayoutEffect(() => {
    if (textareaRef.current) fitTextarea(textareaRef.current);
  }, [input]);

  const fileInputRef = useRef<HTMLInputElement>(null);

  // A pasted PGN or FEN (or a .pgn file) goes to the board directly and the
  // coach is told about it in one short line — the student should not have to
  // ask the model to "load this" and wait for a tool round-trip.
  /** One local line in the thread (no server round-trip) — what the board just did. */
  const addLocalLine = useCallback((content: string, id?: string) => {
    const line: CoachMessage = { id: id ?? crypto.randomUUID(), role: 'user', content, timestamp: new Date() };
    setMessages((prev) => [...prev, line]);
    return line.id;
  }, []);

  const replaceLocalLine = useCallback((id: string, content: string) => {
    setMessages((prev) => prev.map((m) => (m.id === id ? { ...m, content } : m)));
  }, []);

  // A pasted game link: Hermes fetches the PGN (Lichess export / Chess.com
  // callback), the board loads it, the coach sees the new position next turn.
  const loadGameFromUrl = useCallback(
    async (url: string) => {
      const lineId = addLocalLine(t('loadingUrl'));
      try {
        const res = await fetch('/api/coach/import-url', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify({ url }),
        });
        const data = (await res.json().catch(() => ({}))) as {
          pgn?: string; white?: string; black?: string; error?: string;
        };
        if (!res.ok || !data.pgn) {
          replaceLocalLine(lineId, t('urlFailed', { reason: data.error || `HTTP ${res.status}` }));
          return;
        }
        onBoardActions([{ type: 'load_pgn', pgn: data.pgn }]);
        replaceLocalLine(lineId, t('loadedFromUrl', { white: data.white ?? '?', black: data.black ?? '?' }));
      } catch (err: unknown) {
        const reason = err instanceof Error ? err.message : t('unknownError');
        replaceLocalLine(lineId, t('urlFailed', { reason }));
      }
    },
    [addLocalLine, replaceLocalLine, onBoardActions, t],
  );

  const loadPastedGame = useCallback(
    (text: string) => {
      const kind = classifyPastedText(text);
      const trimmed = text.trim();
      if (kind === 'pgn') {
        const pgn = normalizeRussianSan(trimmed);
        if (!isReadablePgn(pgn)) {
          // Say so and keep the text: it can still go to the coach as a message.
          addLocalLine(t('pgnUnreadable'));
          setInput((prev) => prev + trimmed);
          return;
        }
        onBoardActions([{ type: 'load_pgn', pgn }]);
        addLocalLine(t('loadedPgn'));
      } else if (kind === 'fen') {
        onBoardActions([{ type: 'set_fen', fen: trimmed }]);
        addLocalLine(t('loadedFen'));
      } else if (kind === 'url') {
        void loadGameFromUrl(trimmed);
      } else {
        setInput((prev) => prev + trimmed);
      }
    },
    [onBoardActions, t, addLocalLine, loadGameFromUrl],
  );

  // A photo of a board (→ FEN) or of a paper scoresheet (→ PGN), through the
  // site's existing vision routes; the result lands on the board like a paste.
  const photoInputRef = useRef<HTMLInputElement>(null);
  const [photoMode, setPhotoMode] = useState<'position' | 'scoresheet' | null>(null);
  const [attachOpen, setAttachOpen] = useState(false);
  const [photoBusy, setPhotoBusy] = useState(false);
  // A photo does not show whose move it is: the board gets White to move and the
  // next short «ход чёрных» / "black to move" switches it instead of going to the
  // coach (2026-10-06 — the model used to guess the side, half the time wrongly).
  const photoTurnPendingRef = useRef(false);

  const pickPhoto = useCallback((mode: 'position' | 'scoresheet') => {
    setPhotoMode(mode);
    // Let React apply the mode before the native picker opens.
    setTimeout(() => photoInputRef.current?.click(), 0);
  }, []);

  const recognizePhoto = useCallback(
    async (file: File, mode: 'position' | 'scoresheet') => {
      const dataUrl = await new Promise<string>((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(String(reader.result ?? ''));
        reader.onerror = () => reject(reader.error ?? new Error('read failed'));
        reader.readAsDataURL(file);
      });
      const base64 = dataUrlToBase64(dataUrl);
      const lineId = addLocalLine(t('recognizingPhoto'));
      setPhotoBusy(true);
      try {
        if (mode === 'position') {
          const res = await fetch('/api/convert-image', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ image: base64 }),
          });
          const data = (await res.json().catch(() => ({}))) as { fen?: string; turn_known?: boolean; error?: string };
          if (!res.ok || !data.fen) {
            replaceLocalLine(lineId, t('photoFailed', { reason: data.error || `HTTP ${res.status}` }));
            return;
          }
          onBoardActions([{ type: 'set_fen', fen: data.fen }]);
          if (data.turn_known === false) {
            photoTurnPendingRef.current = true;
            replaceLocalLine(lineId, t('loadedFromPhotoTurnUnknown'));
          } else {
            replaceLocalLine(lineId, t('loadedFromPhoto'));
          }
        } else {
          const res = await fetch('/api/convert-scoresheet', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ images: [base64] }),
          });
          const data = (await res.json().catch(() => ({}))) as { pgn?: string; error?: string };
          if (!res.ok || !data.pgn) {
            replaceLocalLine(lineId, t('photoFailed', { reason: data.error || `HTTP ${res.status}` }));
            return;
          }
          onBoardActions([{ type: 'load_pgn', pgn: data.pgn }]);
          replaceLocalLine(lineId, t('loadedFromScoresheet'));
        }
      } catch (err: unknown) {
        const reason = err instanceof Error ? err.message : t('unknownError');
        replaceLocalLine(lineId, t('photoFailed', { reason }));
      } finally {
        setPhotoBusy(false);
      }
    },
    [addLocalLine, replaceLocalLine, onBoardActions, t],
  );

  const sendMessage = useCallback(async (overrideText?: string) => {
    const source = typeof overrideText === 'string' ? overrideText : input;
    const trimmed = source.trim();
    if (!trimmed || isStreaming) return;

    // «ход чёрных» right after a photo with no visible turn: switch the side to
    // move on the board, locally — not a question for the coach.
    if (photoTurnPendingRef.current) {
      const side = sideToMoveCommand(trimmed);
      photoTurnPendingRef.current = false;
      if (side) {
        const flipped = withSideToMove(currentFenRef.current, side);
        if (typeof overrideText !== 'string') setInput('');
        addLocalLine(trimmed);
        if (flipped) {
          onBoardActions([{ type: 'set_fen', fen: flipped }]);
          addLocalLine(t(side === 'w' ? 'whiteToMoveSet' : 'blackToMoveSet'));
        } else {
          addLocalLine(t('sideToMoveImpossible'));
        }
        return;
      }
    }

    const userMessage: CoachMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      fen: currentFen,
      timestamp: new Date(),
    };

    stickRef.current = true;
    setMessages((prev) => [...prev, userMessage]);
    // Only clear the composer when the send came from it (not a starter chip).
    if (typeof overrideText !== 'string') setInput('');
    setIsStreaming(true);

    const assistantId = crypto.randomUUID();
    setMessages((prev) => [
      ...prev,
      { id: assistantId, role: 'assistant', content: '', timestamp: new Date() },
    ]);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const response = await fetch('/api/coach/chat', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          // The visible bubble shows `trimmed`; the coach receives the grounding
          // preamble (if any) prepended so the answer is scoped to the position.
          message: trimmed,
          // Grounding travels apart from the question so Hermes routes, selects
          // tools and stores history on what the student actually asked.
          context_note: contextNote || undefined,
          fen: currentFen,
          session_id: sessionId,
          board_id: boardId || undefined,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
        if (await handleRestrictedResponse(response)) return;
        throw new Error(`HTTP ${response.status}`);
      }

      const reader = response.body?.getReader();
      if (!reader) throw new Error('No response body');

      const decoder = new TextDecoder();
      let buffer = '';
      let fullContent = '';

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;

        buffer += decoder.decode(value, { stream: true });
        const lines = buffer.split('\n');
        buffer = lines.pop() || '';

        for (const line of lines) {
          if (!line.startsWith('data: ')) continue;

          try {
            const data = JSON.parse(line.slice(6));

            // The message's own data (text, stages, cards, board actions, turn id).
            setMessages((prev) => prev.map((m) => (m.id === assistantId ? applyStreamFrame(m, data) : m)));
            if (data.delta) fullContent += data.delta;

            if (data.tool_call) {
              setToolActive(data.tool_call);
            }

            if (data.tool_result) {
              setToolActive(null);
            }

            if (data.board_actions) {
              onBoardActions(data.board_actions);
            }

            if (data.session_id && onSessionCreated) {
              // This chat holds the conversation already (with game cards the
              // server copy lacks) — don't reload it for its own new session.
              restoredForRef.current = data.session_id;
              onSessionCreated(data.session_id);
            }

            if (data.done) {
              setToolActive(null);
              if (data.active_board_id && onActiveBoardChanged) {
                onActiveBoardChanged(data.active_board_id);
              }
            }

            if (data.error) {
              const note = `\n\n*${t('errorLabel')}: ${data.error}*`;
              fullContent += note;
              setMessages((prev) =>
                prev.map((m) => (m.id === assistantId ? { ...m, content: m.content + note } : m))
              );
            }
          } catch {
            // Non-JSON line, skip
          }
        }
      }
      if (fullContent) onAssistantReplyRef.current?.(fullContent);
    } catch (err: unknown) {
      if (err instanceof DOMException && err.name === 'AbortError') {
        // User cancelled
      } else {
        const message = err instanceof Error ? err.message : t('unknownError');
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `*${t('connectionErrorLabel')}: ${message}*` }
              : m
          )
        );
      }
    } finally {
      setIsStreaming(false);
      setToolActive(null);
      abortRef.current = null;
    }
  }, [input, isStreaming, currentFen, sessionId, boardId, onBoardActions, onSessionCreated, onActiveBoardChanged, t, contextNote, addLocalLine]);

  // A streamed assistant message that did not come from the student's question
  // (the coach's remark during a game). Same SSE frames as the chat: `delta`s
  // into one bubble, `error` as the answer text.
  const streamAssistant = useCallback(
    async (url: string, body: Record<string, unknown>) => {
      const assistantId = crypto.randomUUID();
      setMessages((prev) => [...prev, { id: assistantId, role: 'assistant', content: '', timestamp: new Date() }]);
      let content = '';
      const patch = (text: string) =>
        setMessages((prev) => prev.map((m) => (m.id === assistantId ? { ...m, content: text } : m)));
      try {
        const response = await fetch(url, {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(body),
        });
        const reader = response.body?.getReader();
        if (!response.ok || !reader) throw new Error(`HTTP ${response.status}`);
        const decoder = new TextDecoder();
        let buffer = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buffer += decoder.decode(value, { stream: true });
          const lines = buffer.split('\n');
          buffer = lines.pop() || '';
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const data = JSON.parse(line.slice(6));
              if (data.delta) {
                content += data.delta;
                patch(content);
              }
              if (data.error) {
                content += `${content ? '\n\n' : ''}*${t('errorLabel')}: ${data.error}*`;
                patch(content);
              }
            } catch {
              // skip non-JSON
            }
          }
        }
        if (!content) setMessages((prev) => prev.filter((m) => m.id !== assistantId));
        else onAssistantReplyRef.current?.(content);
      } catch (err: unknown) {
        const message = err instanceof Error ? err.message : t('unknownError');
        patch(`*${t('connectionErrorLabel')}: ${message}*`);
      }
    },
    [t],
  );

  // Let a host drive a send (Review Coach Drawer starter chips) or show a
  // streamed remark (game mode).
  useImperativeHandle(
    ref,
    () => ({
      send: (text: string) => {
        void sendMessage(text);
      },
      streamAssistant,
      openAttach: () => setAttachOpen(true),
    }),
    [sendMessage, streamAssistant],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      const coarse = typeof window !== 'undefined' && !!window.matchMedia?.('(pointer: coarse)').matches;
      if (shouldSendOnEnter(e.nativeEvent, coarse)) {
        e.preventDefault();
        sendMessage();
      }
    },
    [sendMessage]
  );

  const handleAbort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  // «Paste PGN/FEN» and «Link» in the attach sheet: read the clipboard when the
  // browser allows it; otherwise the field asks for a paste (onPaste loads it).
  const [pasteHint, setPasteHint] = useState(false);
  const pasteFromClipboard = useCallback(async () => {
    let text = '';
    try {
      text = (await navigator.clipboard?.readText?.()) ?? '';
    } catch {
      text = '';
    }
    if (text && classifyPastedText(text)) {
      loadPastedGame(text);
      return;
    }
    setPasteHint(true);
    textareaRef.current?.focus();
  }, [loadPastedGame]);

  const handleAttach = useCallback(
    (kind: AttachKind) => {
      if (kind === 'upload') fileInputRef.current?.click();
      else if (kind === 'photo-position') pickPhoto('position');
      else if (kind === 'photo-scoresheet') pickPhoto('scoresheet');
      else void pasteFromClipboard();
    },
    [pickPhoto, pasteFromClipboard],
  );

  // The history comes into view (peek → thread): start at the latest message.
  useLayoutEffect(() => {
    if (view === 'thread') scrollToBottom();
  }, [view, scrollToBottom]);

  // Before the first answer: the starter prompts. After it: chips from the
  // latest answer's card, the mode and the board (lib/coach/context-chips.ts).
  const starterPrompts = useStarterPrompts();
  const lastAnswer = [...messages].reverse().find((m) => m.role === 'assistant');
  const prompts = lastAnswer
    ? contextChips({
        mode,
        lastSummaryKind: lastAnswer.summaries?.at(-1)?.kind ?? null,
        gameLoaded: !!currentPgn?.trim(),
      }).map((key) => t(key))
    : starterPrompts;
  const peek = view === 'peek';

  return (
    // ph-no-capture: masks the chat + voice-mode UI from PostHog session replay (kids' privacy).
    // coach-theme: the colour variables, also where the chat is hosted outside /coach (review drawer).
    <div className="coach-theme ph-no-capture flex h-full flex-col bg-(--coach-surface)">
      <MessageList
        messages={messages}
        sessionId={sessionId}
        toolActive={toolActive}
        isStreaming={isStreaming}
        onOpenGame={onOpenGame}
        onSend={(prompt) => void sendMessage(prompt)}
        boardFen={currentFen}
        onBoardActions={onBoardActions}
        onShowBoard={onShowBoard}
        onStartMoments={onStartMoments}
        chips={lastAnswer ? prompts : []}
        scrollRef={scrollRef}
        onScroll={handleScroll}
        hasUnseen={hasUnseen}
        onJumpDown={scrollToBottom}
        hidden={peek}
      />
      {peek && !footer && (
        <div className="flex min-h-0 flex-1 flex-col justify-between gap-3 px-4 pt-1">
          <PeekMessage messages={messages} onExpand={() => onExpand?.()} />
          <ChipRow prompts={prompts} disabled={isStreaming} onSend={(prompt) => void sendMessage(prompt)} />
        </div>
      )}
      {footer && <div className={`shrink-0 px-3 pt-2 ${peek ? 'min-h-0 flex-1 overflow-y-auto' : ''}`}>{footer}</div>}

      {/* Load a .pgn file straight onto the board — no model call needed. */}
      <input
        ref={fileInputRef}
        type="file"
        accept=".pgn,text/plain"
        className="hidden"
        data-testid="pgn-file-input"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = '';
          if (!file) return;
          const text = await file.text();
          loadPastedGame(text);
        }}
      />
      {/* A photo of the board → position, or of a scoresheet → game, via the
          site's vision routes. Same result as a paste: the board changes and
          one line in the thread says what happened. */}
      <input
        ref={photoInputRef}
        type="file"
        accept="image/*"
        className="hidden"
        data-testid="photo-input"
        onChange={async (e) => {
          const file = e.target.files?.[0];
          e.target.value = '';
          if (!file || !photoMode) return;
          await recognizePhoto(file, photoMode);
        }}
      />
      <Composer
        input={input}
        onInputChange={(value) => {
          setInput(value);
          setPasteHint(false);
        }}
        textareaRef={textareaRef}
        placeholder={pasteHint ? t('attachPastePlaceholder') : t('inputPlaceholder')}
        onKeyDown={handleKeyDown}
        onPasteText={(text) => {
          setPasteHint(false);
          if (!classifyPastedText(text)) return false;
          loadPastedGame(text);
          return true;
        }}
        onFocus={() => {
          onComposerFocus?.();
          // The keyboard slides up for ~300 ms; then show the latest message.
          setTimeout(scrollToBottom, 350);
        }}
        isStreaming={isStreaming}
        onSend={() => void sendMessage()}
        onAbort={handleAbort}
        attachOpen={attachOpen}
        onAttachOpenChange={setAttachOpen}
        attachDisabled={isStreaming || photoBusy}
        onAttach={handleAttach}
        voice={{
          supported: voiceSupported,
          status: voiceStatus,
          active: voiceActive,
          error: voiceError,
          quotaExhausted: voiceQuotaExhausted,
          remainingSeconds: voiceRemainingSeconds,
          onToggle: () => void toggleVoice(),
          onPrefetch: prefetchVoice,
        }}
        hidden={composerHidden}
      />
    </div>
  );
});

export default CoachChat;
