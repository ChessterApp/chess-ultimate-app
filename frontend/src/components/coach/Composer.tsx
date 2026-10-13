'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { ArrowUp, Loader2, Mic, Plus, Square } from 'lucide-react';
import type { LiveStatus } from '@/hooks/useGeminiLive';
import AttachSheet, { type AttachKind } from './AttachSheet';

export type ComposerButton = 'stop' | 'send' | 'mic';

/**
 * The composer's one right-hand button: ■ while an answer streams, the mic
 * while voice is on (to end it) or the field is empty, ↑ once there is text.
 * Without voice support an empty field shows a disabled ↑.
 */
export function composerButton({
  hasText,
  streaming,
  voiceSupported,
  voiceActive,
}: {
  hasText: boolean;
  streaming: boolean;
  voiceSupported: boolean;
  voiceActive: boolean;
}): ComposerButton {
  if (streaming) return 'stop';
  if (voiceSupported && (voiceActive || !hasText)) return 'mic';
  return 'send';
}

export interface ComposerVoice {
  supported: boolean;
  status: LiveStatus;
  active: boolean;
  error: string | null;
  quotaExhausted: boolean;
  remainingSeconds: number | null;
  onToggle: () => void;
  onPrefetch: () => void;
}

interface ComposerProps {
  input: string;
  onInputChange: (value: string) => void;
  textareaRef: React.RefObject<HTMLTextAreaElement | null>;
  placeholder: string;
  onKeyDown: (e: React.KeyboardEvent<HTMLTextAreaElement>) => void;
  /** A paste the host loads itself (PGN / FEN / link) returns true. */
  onPasteText: (text: string) => boolean;
  onFocus?: () => void;
  isStreaming: boolean;
  onSend: () => void;
  onAbort: () => void;
  attachOpen: boolean;
  onAttachOpenChange: (open: boolean) => void;
  attachDisabled: boolean;
  onAttach: (kind: AttachKind) => void;
  voice: ComposerVoice;
  hidden?: boolean;
}

const iconButton =
  'flex h-11 w-11 shrink-0 items-center justify-center rounded-full transition-colors focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent) disabled:cursor-not-allowed disabled:opacity-40';

/** One pill: `+` (attach sheet) · auto-growing field · mic / send / stop. */
export default function Composer({
  input,
  onInputChange,
  textareaRef,
  placeholder,
  onKeyDown,
  onPasteText,
  onFocus,
  isStreaming,
  onSend,
  onAbort,
  attachOpen,
  onAttachOpenChange,
  attachDisabled,
  onAttach,
  voice,
  hidden = false,
}: ComposerProps) {
  const t = useTranslations('coach');
  const button = composerButton({
    hasText: !!input.trim(),
    streaming: isStreaming,
    voiceSupported: voice.supported,
    voiceActive: voice.active,
  });
  const voiceLive = voice.status === 'connecting' || voice.status === 'listening' || voice.status === 'speaking';

  return (
    <div className={`px-3 pt-2 pb-3 ${hidden && !voice.active ? 'hidden' : ''}`} data-testid="coach-composer">
      {voiceLive && (
        <div className="mb-2 flex justify-center">
          <span data-testid="voice-pill" className="rounded-full bg-(--coach-surface-2) px-3 py-1 text-xs text-(--coach-text)">
            {voice.status === 'connecting'
              ? t('voiceConnecting')
              : voice.status === 'listening'
                ? t('voiceListening')
                : t('voiceSpeaking')}
          </span>
        </div>
      )}
      {/* The error is shown here, not only in the mic tooltip (invisible on touch). */}
      {voice.status === 'error' && (
        <div className="mb-2 flex justify-center">
          <span data-testid="voice-pill" className="rounded-full bg-(--coach-danger-soft) px-3 py-1 text-center text-xs text-(--coach-danger)">
            {(voice.error || t('voiceError')) + ' · ' + t('voiceRetryHint')}
          </span>
        </div>
      )}
      {/* Monthly voice minutes ran out — text chat stays unlimited. */}
      {voice.quotaExhausted && (
        <div className="mb-2 flex justify-center">
          <span data-testid="voice-quota-pill" className="rounded-full bg-amber-500/10 px-3 py-1 text-center text-xs text-amber-300">
            {t('voiceQuotaExhausted')}
          </span>
        </div>
      )}
      {/* Remaining voice minutes; warns at ≤5 min left. */}
      {voice.active && voice.remainingSeconds !== null && (
        <div className="mb-2 flex justify-center">
          <span
            data-testid="voice-minutes-left"
            className={`rounded-full px-3 py-1 text-xs ${
              voice.remainingSeconds <= 5 * 60 ? 'bg-amber-500/10 text-amber-300' : 'bg-(--coach-surface-2) text-(--coach-text)'
            }`}
          >
            {t('voiceMinutesLeft', { minutes: Math.ceil(voice.remainingSeconds / 60) })}
          </span>
        </div>
      )}

      <div className="relative flex items-end gap-1 rounded-[26px] border border-(--coach-border) bg-(--coach-surface-2) p-1 transition-colors focus-within:border-(--coach-accent)">
        <button
          type="button"
          onClick={() => onAttachOpenChange(!attachOpen)}
          disabled={attachDisabled}
          aria-label={t('attachMenu')}
          aria-haspopup="menu"
          aria-expanded={attachOpen}
          title={t('attachMenu')}
          className={`${iconButton} text-(--coach-text) hover:bg-white/5`}
        >
          <Plus size={22} aria-hidden />
        </button>
        <AttachSheet open={attachOpen} onClose={() => onAttachOpenChange(false)} onPick={onAttach} />

        <textarea
          ref={textareaRef}
          value={input}
          onChange={(e) => onInputChange(e.target.value)}
          onKeyDown={onKeyDown}
          onPaste={(e) => {
            if (onPasteText(e.clipboardData.getData('text'))) e.preventDefault();
          }}
          onFocus={onFocus}
          placeholder={placeholder}
          aria-label={placeholder}
          rows={1}
          // 16px on phones: iOS Safari zooms the whole page into a smaller field.
          className="min-w-0 flex-1 resize-none bg-transparent px-1 py-2.5 text-base leading-6 text-(--coach-text) placeholder-(--coach-muted) focus:outline-none sm:text-[15px]"
          disabled={isStreaming}
        />

        {button === 'stop' ? (
          <button
            type="button"
            onClick={onAbort}
            title={t('stopTooltip')}
            aria-label={t('stopTooltip')}
            data-testid="composer-stop"
            className={`${iconButton} bg-(--coach-text) text-(--coach-bg)`}
          >
            <Square size={14} fill="currentColor" aria-hidden />
          </button>
        ) : button === 'send' ? (
          <button
            type="button"
            onClick={onSend}
            disabled={!input.trim()}
            title={t('sendTooltip')}
            aria-label={t('sendTooltip')}
            data-testid="composer-send"
            className={`${iconButton} bg-(--coach-text) text-(--coach-bg) hover:opacity-90`}
          >
            <ArrowUp size={20} aria-hidden />
          </button>
        ) : (
          <button
            type="button"
            onClick={voice.onToggle}
            onPointerEnter={voice.onPrefetch}
            onPointerDown={voice.onPrefetch}
            onFocus={voice.onPrefetch}
            disabled={voice.status === 'connecting'}
            data-testid="voice-toggle"
            data-status={voice.status}
            aria-label={voice.active ? t('voiceStop') : t('voiceStart')}
            title={voice.status === 'error' && voice.error ? voice.error : voice.active ? t('voiceStop') : t('voiceStart')}
            className={`${iconButton} ${
              voice.status === 'listening'
                ? 'animate-pulse bg-(--coach-success-soft) text-(--coach-success) ring-2 ring-(--coach-success)/50'
                : voice.status === 'speaking'
                  ? 'animate-pulse bg-(--coach-accent-soft) text-(--coach-accent-text) ring-2 ring-(--coach-accent)/50'
                  : voice.status === 'error'
                    ? 'bg-(--coach-danger-soft) text-(--coach-danger)'
                    : 'bg-(--coach-text) text-(--coach-bg) hover:opacity-90'
            }`}
          >
            {voice.status === 'connecting' ? <Loader2 size={18} className="animate-spin" aria-hidden /> : <Mic size={18} aria-hidden />}
          </button>
        )}
      </div>
    </div>
  );
}
