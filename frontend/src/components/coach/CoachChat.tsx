'use client';

import React, { useState, useRef, useCallback, useEffect } from 'react';
import ReactMarkdown from 'react-markdown';
import ToolIndicator from './ToolIndicator';
import type { CoachMessage, BoardAction } from '@/types/coach';

interface CoachChatProps {
  currentFen: string;
  sessionId: string | null;
  onBoardActions: (actions: BoardAction[]) => void;
  onSessionCreated?: (id: string) => void;
}

export default function CoachChat({
  currentFen,
  sessionId,
  onBoardActions,
  onSessionCreated,
}: CoachChatProps) {
  const [messages, setMessages] = useState<CoachMessage[]>([]);
  const [input, setInput] = useState('');
  const [isStreaming, setIsStreaming] = useState(false);
  const [toolActive, setToolActive] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  const scrollToBottom = useCallback(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  }, []);

  useEffect(() => {
    scrollToBottom();
  }, [messages, scrollToBottom]);

  const sendMessage = useCallback(async () => {
    const trimmed = input.trim();
    if (!trimmed || isStreaming) return;

    const userMessage: CoachMessage = {
      id: crypto.randomUUID(),
      role: 'user',
      content: trimmed,
      fen: currentFen,
      timestamp: new Date(),
    };

    setMessages((prev) => [...prev, userMessage]);
    setInput('');
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
          message: trimmed,
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

            if (data.session_id && onSessionCreated) {
              onSessionCreated(data.session_id);
            }

            if (data.done) {
              setToolActive(null);
            }

            if (data.error) {
              fullContent += `\n\n*Error: ${data.error}*`;
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
        const message = err instanceof Error ? err.message : 'Unknown error';
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId
              ? { ...m, content: `*Connection error: ${message}*` }
              : m
          )
        );
      }
    } finally {
      setIsStreaming(false);
      setToolActive(null);
      abortRef.current = null;
    }
  }, [input, isStreaming, currentFen, sessionId, onBoardActions, onSessionCreated]);

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
            <p className="text-lg font-medium text-gray-400">AI Chess Coach</p>
            <p className="text-sm mt-1">
              Ask me anything about chess — positions, openings, tactics, or strategy.
            </p>
            <div className="mt-6 flex flex-wrap gap-2 justify-center">
              {[
                'Analyze this position',
                'Show me the Sicilian Defense',
                'Give me a tactical puzzle',
                'Explain pawn structures',
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
                  Board updated
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
        <div className="flex gap-2">
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask your coach..."
            rows={1}
            className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm text-gray-100 placeholder-gray-500 resize-none focus:outline-none focus:border-blue-500/50"
            disabled={isStreaming}
          />
          {isStreaming ? (
            <button
              onClick={handleAbort}
              className="px-4 py-2 bg-red-500/20 hover:bg-red-500/30 text-red-400 rounded-lg transition-colors"
              title="Stop"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <rect x="3" y="3" width="10" height="10" rx="1" />
              </svg>
            </button>
          ) : (
            <button
              onClick={sendMessage}
              disabled={!input.trim()}
              className="px-4 py-2 bg-blue-600/30 hover:bg-blue-600/50 text-blue-300 rounded-lg transition-colors disabled:opacity-30 disabled:cursor-not-allowed"
              title="Send (Enter)"
            >
              <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
                <path d="M1 1l14 7-14 7V9l10-1-10-1V1z" />
              </svg>
            </button>
          )}
        </div>
      </div>
    </div>
  );
}
