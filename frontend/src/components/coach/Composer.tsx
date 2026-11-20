'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import { ArrowUp, Loader2, Mic, Plus, Square } from 'lucide-react';
import type { LiveStatus } from '@/hooks/useGeminiLive';
import type { VoiceStage } from '@/hooks/usePipelineVoice';
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

/** While voice is on the right-hand button ends it; text typed meanwhile gets its own send button beside it —
 * without one it could not be sent at all in the app, where Enter makes a new line (tester, 19.11). */
export function sendBesideMic({ hasText, streaming, voiceActive }: { hasText: boolean; streaming: boolean; voiceActive: boolean }): boolean {
  return voiceActive && hasText && !streaming;
}

export interface ComposerVoice {
  supported: boolean;
  status: LiveStatus;
  active: boolean;
  error: string | null;
  /** What a voice tool just refused («'e4' is not a legal move here»), for a few seconds. */
  notice?: string | null;
  quotaExhausted: boolean;
  remainingSeconds: number | null;
  onToggle: () => void;
  onPrefetch: () => void;
  /** The step of the exchange (the pipeline's; Live has only its status) — the banner over the field. */
  stage?: VoiceStage;
  /** The mic's level now, 0…1 (the pipeline's meter). */
  level?: number;
  /** The words last heard, shown while the coach thinks. */
  heard?: string | null;
}

/** The stage the banner shows: the pipeline's own, else the status (Live). */
export function bannerStage(voice: Pick<ComposerVoice, 'stage' | 'status' | 'active'>): VoiceStage | null {
  const stage = voice.stage ?? (voice.status as VoiceStage);
  if (stage === 'connecting') return stage;
  if (!voice.active) return null;
  return stage === 'idle' || stage === 'error' ? null : stage;
}

/** The stages a wait is counted in, seconds on the banner (tester, 19.11: «долго ждёшь»). */
const COUNTED: VoiceStage[] = ['connecting', 'recognizing', 'thinking'];

/**
 * The voice's banner over the field (tester, 19.11: «непонятно, когда микрофон слушает … не видно, включён он или нет»;
 * Asan: «сделай так, чтобы прям видно было»). A wide card coloured by the step: green while the mic listens or hears
 * the student (a live level meter), the accent while the coach talks, neutral with a seconds count while the words are
 * recognised and the coach thinks — with the words heard, so a misheard phrase is seen at once. «Стоп» ends the voice.
 * The app's voice-controls.tsx VoiceBanner is the same.
 */
export function VoiceBanner({ voice }: { voice: ComposerVoice }) {
  const t = useTranslations('coach');
  const stage = bannerStage(voice);
  const counted = !!stage && COUNTED.includes(stage);
  const [count, setCount] = React.useState<{ stage: VoiceStage | null; seconds: number }>({ stage, seconds: 0 });
  React.useEffect(() => {
    if (!counted) return;
    const timer = setInterval(
      () => setCount((prev) => (prev.stage === stage ? { stage, seconds: prev.seconds + 1 } : { stage, seconds: 1 })),
      1000,
    );
    return () => clearInterval(timer);
  }, [counted, stage]);
  if (!stage) return null;
  const seconds = count.stage === stage ? count.seconds : 0;
  const green = stage === 'listening' || stage === 'hearing';
  const tone = green
    ? 'border-(--coach-success) bg-(--coach-success-soft) text-(--coach-success)'
    : stage === 'speaking'
      ? 'border-(--coach-accent) bg-(--coach-accent-soft) text-(--coach-accent-text)'
      : 'border-(--coach-border) bg-(--coach-surface-2) text-(--coach-text)';
  const title = t(`voiceStage.${stage}`) + (counted && seconds > 0 ? ` · ${seconds} ${t('voiceSeconds')}` : '');
  const sub = stage === 'thinking' && voice.heard ? t('voiceHeard', { text: voice.heard }) : t(`voiceStageHint.${stage}`);
  const level = voice.level ?? 0;
  return (
    <div data-testid="voice-banner" data-stage={stage} role="status" aria-live="polite"
      className={`mb-2 flex items-center gap-3 rounded-2xl border-[1.5px] py-2.5 pr-2.5 pl-3.5 ${tone}`}>
      <div className="flex h-6 w-7 shrink-0 items-center justify-center" aria-hidden>
        {green ? (
          <div className="flex h-6 items-center gap-0.5" data-testid="voice-level">
            {[0.55, 0.8, 1, 0.8, 0.55].map((k, i) => (
              <span key={i} className="w-[3px] rounded-sm bg-current transition-[height] duration-100"
                style={{ height: 4 + Math.round(18 * Math.min(1, level * k * 1.2)) }} />
            ))}
          </div>
        ) : counted ? (
          <Loader2 size={20} className="animate-spin" />
        ) : (
          <Mic size={20} />
        )}
      </div>
      <div className="min-w-0 flex-1">
        <div data-testid="voice-banner-title" className="truncate text-base leading-[22px] font-semibold">{title}</div>
        <div className="line-clamp-2 text-[13px] leading-[18px] text-(--coach-muted)">{sub}</div>
      </div>
      {voice.active && (
        <button type="button" onClick={voice.onToggle} data-testid="voice-banner-stop" aria-label={t('voiceStop')}
          className="flex min-h-10 shrink-0 items-center gap-1.5 rounded-xl bg-(--coach-danger-soft) px-3 text-sm font-semibold text-(--coach-danger) hover:opacity-90">
          <Square size={12} fill="currentColor" aria-hidden />
          {t('voiceStopShort')}
        </button>
      )}
    </div>
  );
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
      {voiceLive && <VoiceBanner voice={voice} />}
      {/* The error is shown here, not only in the mic tooltip (invisible on touch). */}
      {voice.status === 'error' && (
        <div className="mb-2 flex justify-center">
          <span data-testid="voice-pill" className="rounded-full bg-(--coach-danger-soft) px-3 py-1 text-center text-xs text-(--coach-danger)">
            {(voice.error || t('voiceError')) + ' · ' + t('voiceRetryHint')}
          </span>
        </div>
      )}
      {/* A game tool refused what was said: shown here, so a refusal never looks like a board that does not move. */}
      {voice.notice && (
        <div className="mb-2 flex justify-center">
          <span data-testid="voice-notice-pill" className="rounded-full bg-amber-500/10 px-3 py-1 text-center text-xs text-amber-300">
            {voice.notice}
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
          className="min-w-0 flex-1 resize-none bg-transparent px-1 py-2.5 text-base leading-6 text-(--coach-text) placeholder-(--coach-muted) sm:text-[15px]"
          // The pill's accent border shows focus; inline, because the app's
          // unlayered *:focus-visible ring outranks layered utilities.
          style={{ outline: 'none' }}
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
          <>
          {sendBesideMic({ hasText: !!input.trim(), streaming: isStreaming, voiceActive: voice.active }) && (
            <button
              type="button"
              onClick={onSend}
              title={t('sendTooltip')}
              aria-label={t('sendTooltip')}
              data-testid="composer-send"
              className={`${iconButton} bg-(--coach-text) text-(--coach-bg) hover:opacity-90`}
            >
              <ArrowUp size={20} aria-hidden />
            </button>
          )}
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
          </>
        )}
      </div>
    </div>
  );
}
