'use client';

import React, {
  useState,
  useRef,
  useCallback,
  useEffect,
  forwardRef,
  useImperativeHandle,
} from 'react';
import { useTranslations } from 'next-intl';
import ReactMarkdown from 'react-markdown';
import ToolIndicator from './ToolIndicator';
import useGeminiLive from '@/hooks/useGeminiLive';
import type { CoachMessage, BoardAction, GameResult } from '@/types/coach';

interface CoachChatProps {
  currentFen: string;
  sessionId: string | null;
  onBoardActions: (actions: BoardAction[]) => void;
  onSessionCreated?: (id: string) => void;
  onOpenGame?: (game: GameResult) => void;
  /**
   * Optional grounding preamble prepended to the OUTGOING message sent to the
   * coach — never shown in the user's chat bubble. The Review Coach Drawer uses
   * this to scope every question to the move currently under review.
   */
  contextNote?: string;
}

/** Imperative handle so a host (e.g. the Review Coach Drawer) can send a
 * message programmatically — used by the drawer's one-tap starter chips. */
export interface CoachChatHandle {
  send: (text: string) => void;
}

const CoachChat = forwardRef<CoachChatHandle, CoachChatProps>(function CoachChat(
  {
    currentFen,
    sessionId,
    onBoardActions,
    onSessionCreated,
    onOpenGame,
    contextNote,
  },
  ref,
) {
  const t = useTranslations('coach');
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [toolActive, setToolActive] = useState<string | null>(null);
  // Set when the monthly voice quota is exhausted, so we show the "minutes used
  // up — text is unlimited" message in place of a connection error.
  const [voiceQuotaExhausted, setVoiceQuotaExhausted] = useState(false);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // ── Voice mode (Gemini Live) ──────────────────────────────────────────────
  // Keep the latest FEN in a ref so the hook's getFen closure never goes stale.
  const currentFenRef = useRef(currentFen);
  currentFenRef.current = currentFen;
  const getFen = useCallback(() => currentFenRef.current, []);

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
      if (currentId) {
        voiceTextRef.current[tr.role] += tr.text;
        setMessages((prev) =>
          prev.map((m) =>
            m.id === currentId ? { ...m, content: m.content + tr.text } : m
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
          { id, role: mappedRole, content: tr.text, timestamp: new Date() },
        ]);
      }
      if (tr.final) {
        // Persist the finalized utterance into the shared Hermes session so the
        // text coach sees it too. Fire-and-forget: never disrupt the voice call.
        const fullText = voiceTextRef.current[tr.role].trim();
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

  const {
    status: voiceStatus,
    isSupported: voiceSupported,
    isActive: voiceActive,
    error: voiceError,
    prepare: voicePrepare,
    connect: voiceConnect,
    disconnect: voiceDisconnect,
    sendBoardUpdate: voiceSendBoardUpdate,
    remainingSeconds: voiceRemainingSeconds,
  } = useGeminiLive({
    getFen,
    getSessionId,
    onTranscript: handleTranscript,
    onToolResult: handleVoiceToolResult,
    onQuotaExhausted: handleVoiceQuotaExhausted,
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
    await ensureVoiceSession();
    voiceConnect();
  }, [voiceActive, voicePrepare, voiceConnect, voiceDisconnect, ensureVoiceSession]);

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
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const sendMessage = useCallback(async (overrideText?: string) => {
    const source = typeof overrideText === 'string' ? overrideText : input;
    const trimmed = source.trim();
    if (!trimmed || isStreaming) return;

    const userMessage: CoachMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      fen: currentFen,
      timestamp: new Date(),
    };

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
          message: contextNote ? `${contextNote}\n\n${trimmed}` : trimmed,
          fen: currentFen,
          session_id: sessionId,
        }),
        signal: controller.signal,
      });

      if (!response.ok) {
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

            if (data.delta) {
              fullContent += data.delta;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: fullContent } : m
                )
              );
            }

            if (data.tool_call) {
              setToolActive(data.tool_call);
            }

            if (data.tool_result) {
              setToolActive(null);
            }

            if (data.board_actions) {
              onBoardActions(data.board_actions);
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, boardActions: data.board_actions }
                    : m
                )
              );
            }

            if (data.game_results) {
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId
                    ? { ...m, gameResults: data.game_results }
                    : m
                )
              );
            }

            if (data.session_id && onSessionCreated) {
              onSessionCreated(data.session_id);
            }

            if (data.done) {
              setToolActive(null);
            }

            if (data.error) {
              fullContent += `\n\n*${t('errorLabel')}: ${data.error}*`;
              setMessages((prev) =>
                prev.map((m) =>
                  m.id === assistantId ? { ...m, content: fullContent } : m
                )
              );
            }
          } catch {
            // Non-JSON line, skip
          }
        }
      }
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
  }, [input, isStreaming, currentFen, sessionId, onBoardActions, onSessionCreated, t, contextNote]);

  // Let a host drive a send (Review Coach Drawer starter chips).
  useImperativeHandle(
    ref,
    () => ({
      send: (text: string) => {
        void sendMessage(text);
      },
    }),
    [sendMessage],
  );

  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
      if (e.key === 'Enter' && !e.shiftKey) {
        e.preventDefault();
        sendMessage();
      }
    },
    [sendMessage]
  );

  const handleAbort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  return (
    <div className="flex flex-col h-full" style={{ background: '#16213e' }}>
      {/* Messages */}
      <div className="flex-1 overflow-y-auto px-4 py-3 space-y-4">
        {messages.length === 0 && (
          <div className="text-center text-gray-500 mt-8">
            <div className="text-4xl mb-3">♞</div>
            <p className="text-lg font-medium text-gray-400">{t('emptyTitle')}</p>
            <p className="text-sm mt-1">
              {t('emptySubtitle')}
            </p>
            <div className="mt-6 flex flex-wrap gap-2 justify-center">
              {[
                t('promptAnalyze'),
                t('promptSicilian'),
                t('promptPuzzle'),
                t('promptPawnStructures'),
              ].map((prompt) => (
                <button
                  key={prompt}
                  onClick={() => setInput(prompt)}
                  className="px-3 py-1.5 text-sm bg-white/5 hover:bg-white/10 rounded-lg text-gray-400 transition-colors"
                >
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg) => (
          <div
            key={msg.id}
            className={`flex ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}
          >
            <div
              className={`max-w-[85%] rounded-xl px-4 py-2.5 ${
                msg.role === 'user'
                  ? 'bg-blue-600/30 text-gray-100'
                  : 'bg-white/5 text-gray-200'
              }`}
            >
              {msg.role === 'assistant' ? (
                <div className="prose prose-invert prose-sm max-w-none">
                  <ReactMarkdown>{msg.content || '...'}</ReactMarkdown>
                </div>
              ) : (
                <p className="text-sm whitespace-pre-wrap">{msg.content}</p>
              )}
              {msg.boardActions && msg.boardActions.length > 0 && (
                <div className="mt-1.5 text-xs text-gray-500 flex items-center gap-1">
                  <svg width="12" height="12" viewBox="0 0 16 16" fill="currentColor">
                    <path d="M8 0a8 8 0 100 16A8 8 0 008 0zm1 12H7V7h2v5zm0-7H7V3h2v2z" />
                  </svg>
                  {t('boardUpdated')}
                </div>
              )}
              {msg.gameResults && msg.gameResults.length > 0 && (
                <div className="mt-3 rounded-lg overflow-hidden border border-white/10">
                  <table className="w-full text-xs">
                    <thead>
                      <tr className="bg-white/5 text-gray-400">
                        <th className="px-2 py-1.5 text-left">{t('tableDate')}</th>
                        <th className="px-2 py-1.5 text-left">{t('tableWhite')}</th>
                        <th className="px-2 py-1.5 text-left">{t('tableBlack')}</th>
                        <th className="px-2 py-1.5 text-center">{t('tableResult')}</th>
                        <th className="px-2 py-1.5 text-left">{t('tableEco')}</th>
                      </tr>
                    </thead>
                    <tbody>
                      {msg.gameResults.map((game) => (
                        <tr
                          key={game.id}
                          onClick={() => onOpenGame?.(game)}
                          className="hover:bg-white/10 cursor-pointer transition-colors border-t border-white/5"
                        >
                          <td className="px-2 py-1.5 text-gray-400">{game.date}</td>
                          <td className="px-2 py-1.5 text-gray-200">
                            {game.white_name} <span className="text-gray-500">{game.white_elo}</span>
                          </td>
                          <td className="px-2 py-1.5 text-gray-200">
                            {game.black_name} <span className="text-gray-500">{game.black_elo}</span>
                          </td>
                          <td className="px-2 py-1.5 text-center">
                            <span className={
                              game.result === '1-0' ? 'text-green-400' :
                              game.result === '0-1' ? 'text-red-400' :
                              'text-gray-400'
                            }>{game.result}</span>
                          </td>
                          <td className="px-2 py-1.5 text-gray-400">{game.eco}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </div>
        ))}

        <ToolIndicator toolName={toolActive || ''} visible={!!toolActive} />
        <div ref={messagesEndRef} />
      </div>

      {/* Input */}
      <div className="border-t border-white/10 p-3">
        {(voiceStatus === 'connecting' ||
          voiceStatus === 'listening' ||
          voiceStatus === 'speaking') && (
          <div className="mb-2 flex justify-center">
            <span
              data-testid="voice-pill"
              className="px-3 py-1 rounded-full text-xs bg-white/5 text-gray-300"
            >
              {voiceStatus === 'connecting'
                ? t('voiceConnecting')
                : voiceStatus === 'listening'
                  ? t('voiceListening')
                  : t('voiceSpeaking')}
            </span>
          </div>
        )}
        {/* Error state is surfaced visibly here (not only in the mic tooltip,
            which is invisible on touch devices). Shows the real error + a
            tap-to-retry hint. */}
        {voiceStatus === 'error' && (
          <div className="mb-2 flex justify-center">
            <span
              data-testid="voice-pill"
              className="px-3 py-1 rounded-full text-xs bg-red-500/10 text-red-300 text-center"
            >
              {(voiceError || t('voiceError')) + ' · ' + t('voiceRetryHint')}
            </span>
          </div>
        )}
        {/* Monthly voice minutes ran out — text chat stays unlimited. */}
        {voiceQuotaExhausted && (
          <div className="mb-2 flex justify-center">
            <span
              data-testid="voice-quota-pill"
              className="px-3 py-1 rounded-full text-xs bg-amber-500/10 text-amber-300 text-center"
            >
              {t('voiceQuotaExhausted')}
            </span>
          </div>
        )}
        {/* Remaining voice minutes near the toggle; warns at ≤5 min left. */}
        {voiceActive && voiceRemainingSeconds !== null && (
          <div className="mb-2 flex justify-center">
            <span
              data-testid="voice-minutes-left"
              className={`px-3 py-1 rounded-full text-xs ${
                voiceRemainingSeconds <= 5 * 60
                  ? 'bg-amber-500/10 text-amber-300'
                  : 'bg-white/5 text-gray-300'
              }`}
            >
              {t('voiceMinutesLeft', {
                minutes: Math.ceil(voiceRemainingSeconds / 60),
              })}
            </span>
          </div>
        )}
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder={t('inputPlaceholder')}
            rows={1}
            className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 resize-none focus:outline-none focus:border-blue-500/50"
            disabled={isStreaming}
          />
          {isStreaming ? (
            <button
              onClick={handleAbort}
              className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-colors"
              title={t('stopTooltip')}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <rect x="3" y="3" width="10" height="10" rx="1" />
              </svg>
            </button>
          ) : (
            <button
              onClick={() => sendMessage()}
              disabled={!input.trim()}
              className="px-4 py-2 bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              title={t('sendTooltip')}
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M1 1l14 7-14 7V9l10-1-10-1V1z" />
              </svg>
            </button>
          )}
          {voiceSupported && (
            <button
              onClick={toggleVoice}
              disabled={voiceStatus === 'connecting'}
              data-testid="voice-toggle"
              data-status={voiceStatus}
              aria-label={voiceActive ? t('voiceStop') : t('voiceStart')}
              title={
                voiceStatus === 'error' && voiceError
                  ? voiceError
                  : voiceActive
                    ? t('voiceStop')
                    : t('voiceStart')
              }
              className={`px-4 py-2 rounded-lg transition-colors disabled:cursor-not-allowed ${
                voiceStatus === 'listening'
                  ? 'bg-green-500/20 text-green-400 ring-2 ring-green-400/50 animate-pulse'
                  : voiceStatus === 'speaking'
                    ? 'bg-blue-500/20 text-blue-300 ring-2 ring-blue-400/50 animate-pulse'
                    : voiceStatus === 'connecting'
                      ? 'bg-white/10 text-gray-400 animate-pulse'
                      : voiceStatus === 'error'
                        ? 'bg-red-500/20 text-red-400'
                        : 'bg-white/5 hover:bg-white/10 text-gray-400'
              }`}
            >
              {voiceStatus === 'connecting' ? (
                <svg
                  className="animate-spin"
                  width="16"
                  height="16"
                  viewBox="0 0 16 16"
                  fill="none"
                >
                  <circle
                    cx="8"
                    cy="8"
                    r="6"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeOpacity="0.25"
                  />
                  <path
                    d="M14 8a6 6 0 00-6-6"
                    stroke="currentColor"
                    strokeWidth="2"
                    strokeLinecap="round"
                  />
                </svg>
              ) : (
                <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                  <path d="M8 10a2.5 2.5 0 002.5-2.5v-4a2.5 2.5 0 00-5 0v4A2.5 2.5 0 008 10z" />
                  <path d="M12 7.5a.5.5 0 00-1 0 3 3 0 01-6 0 .5.5 0 00-1 0 4 4 0 003.5 3.97V13H6a.5.5 0 000 1h4a.5.5 0 000-1H8.5v-1.53A4 4 0 0012 7.5z" />
                </svg>
              )}
            </button>
          )}
        </div>
      </div>
    </div>
  );
});

export default CoachChat;
