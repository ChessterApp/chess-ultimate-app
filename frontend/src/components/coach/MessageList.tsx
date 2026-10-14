'use client';

import React from 'react';
import { useTranslations } from 'next-intl';
import ReactMarkdown from 'react-markdown';
import type { BoardAction, CoachMessage, GameResult } from '@/types/coach';
import type { ReviewMomentsSummary } from '@/lib/coach/tool-summary';
import type { PlanAction } from '@/lib/coach/daily-plan';
import type { DailyPlanState } from '@/hooks/useDailyPlan';
import DailyPlan, { DailyPlanSkeleton } from './DailyPlan';
import { messageText } from '@/lib/coach/message-stream';
import CoachAvatar from './CoachAvatar';
import FeedbackButtons from './FeedbackButtons';
import ToolIndicator from './ToolIndicator';
import MessageCards from './cards/MessageCards';

/**
 * Markdown in an assistant answer: typography's dark scale, sized for chat —
 * tight block margins, no edge margins, inline code as a chip.
 */
const MARKDOWN_CLASSES = [
  'prose prose-invert prose-sm max-w-none text-(--coach-text)',
  'prose-p:my-1.5 prose-ul:my-1.5 prose-ol:my-1.5 prose-li:my-0.5 prose-blockquote:my-2',
  'prose-headings:mt-3 prose-headings:mb-1 prose-headings:text-(--coach-text) prose-h1:text-base prose-h2:text-base prose-h3:text-sm',
  'prose-strong:text-(--coach-text) prose-a:text-(--coach-accent-text)',
  'prose-code:font-normal prose-code:before:content-none prose-code:after:content-none',
  '[&_:not(pre)>code]:rounded [&_:not(pre)>code]:bg-white/10 [&_:not(pre)>code]:px-1 [&_:not(pre)>code]:py-0.5',
  'prose-pre:my-2 prose-pre:bg-black/30 prose-pre:px-3 prose-pre:py-2',
  '[&>:first-child]:mt-0 [&>:last-child]:mb-0',
].join(' ');

/** The four starter prompts: the empty thread's chips and the peek's chip row. */
export function useStarterPrompts(): string[] {
  const t = useTranslations('coach');
  return [t('promptAnalyze'), t('promptSicilian'), t('promptPuzzle'), t('promptPawnStructures')];
}

const chipBase =
  'min-h-11 shrink-0 rounded-full border bg-(--coach-surface-2) px-3.5 text-[13.5px] font-medium transition-colors hover:border-(--coach-accent) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent) disabled:opacity-40';
const chipClass = `${chipBase} border-(--coach-border) text-(--coach-text)`;
/** The first chip is the suggested one. */
const chipLead = `${chipBase} border-(--coach-accent)/60 text-(--coach-accent-text)`;

/** One row of prompt chips, scrolling sideways; tap sends. */
export function ChipRow({ prompts, disabled, onSend }: { prompts: string[]; disabled: boolean; onSend: (prompt: string) => void }) {
  return (
    <div className="-mx-3 flex gap-2 overflow-x-auto px-3 [scrollbar-width:none]" data-testid="coach-chips">
      {prompts.map((prompt, i) => (
        <button
          key={prompt}
          type="button"
          onClick={() => onSend(prompt)}
          disabled={disabled}
          className={i === 0 ? chipLead : chipClass}
        >
          {prompt}
        </button>
      ))}
    </div>
  );
}

interface MessageListProps {
  messages: CoachMessage[];
  sessionId: string | null;
  toolActive: string | null;
  isStreaming: boolean;
  onOpenGame?: (game: GameResult) => void;
  onSend: (prompt: string) => void;
  /** The study board's position (cards draw on it), and the path their actions take. */
  boardFen: string;
  onBoardActions?: (actions: BoardAction[]) => void;
  /** Bring the board into view (phones: the sheet drops to peek). */
  onShowBoard?: () => void;
  /** «Начать» on a game review card. */
  onStartMoments?: (review: ReviewMomentsSummary) => void;
  /** The empty session's home: today's plan (loading → skeleton, none → the starter prompts). */
  plan?: DailyPlanState;
  greetingName?: string | null;
  onPlanAction?: (action: PlanAction) => void;
  /** Contextual chips under the conversation once it has started. */
  chips: string[];
  scrollRef: React.RefObject<HTMLDivElement | null>;
  onScroll: () => void;
  hasUnseen: boolean;
  onJumpDown: () => void;
  hidden?: boolean;
}

/** The conversation: assistant answers full width, the student's on the right. */
export default function MessageList({
  messages,
  sessionId,
  toolActive,
  isStreaming,
  onOpenGame,
  onSend,
  boardFen,
  onBoardActions,
  onShowBoard,
  onStartMoments,
  plan,
  greetingName,
  onPlanAction,
  chips,
  scrollRef,
  onScroll,
  hasUnseen,
  onJumpDown,
  hidden = false,
}: MessageListProps) {
  const t = useTranslations('coach');
  const prompts = useStarterPrompts();

  return (
    <div className={`relative min-h-0 flex-1 ${hidden ? 'hidden' : ''}`}>
      <div ref={scrollRef} onScroll={onScroll} data-testid="coach-messages" className="h-full space-y-4 overflow-y-auto px-4 py-3">
        {messages.length === 0 && plan?.status === 'loading' && <DailyPlanSkeleton variant="thread" />}
        {messages.length === 0 && plan?.status === 'ready' && onPlanAction && (
          <DailyPlan plan={plan.plan} variant="thread" greetingName={greetingName} disabled={isStreaming} onAction={onPlanAction} />
        )}
        {messages.length === 0 && !(plan?.status === 'loading' || (plan?.status === 'ready' && onPlanAction)) && (
          <div className="mt-8 text-center">
            <div className="mb-3 flex justify-center">
              <CoachAvatar size={56} />
            </div>
            <p className="text-lg font-semibold text-(--coach-text)">{t('emptyTitle')}</p>
            <p className="mt-1 text-sm text-(--coach-muted)">{t('emptySubtitle')}</p>
            <div className="mt-6 flex flex-wrap justify-center gap-2">
              {prompts.map((prompt) => (
                <button key={prompt} type="button" onClick={() => onSend(prompt)} disabled={isStreaming} className={chipClass}>
                  {prompt}
                </button>
              ))}
            </div>
          </div>
        )}

        {messages.map((msg, i) => (
          <div key={msg.id} className={`flex gap-2.5 ${msg.role === 'user' ? 'justify-end' : 'justify-start'}`}>
            {msg.role === 'assistant' && (
              <span className="mt-0.5">
                <CoachAvatar size={28} />
              </span>
            )}
            <div
              className={
                msg.role === 'user'
                  ? 'max-w-[85%] rounded-[18px] rounded-br-[4px] bg-(--coach-accent) px-3.5 py-2 text-white'
                  : 'min-w-0 flex-1 text-(--coach-text)'
              }
            >
              {msg.role === 'assistant' ? (
                <>
                  {/* A two-part answer: the quick reaction is its own line; the answer streams below it. */}
                  {msg.quick && (
                    <p className="text-[15px] font-medium leading-snug text-(--coach-text)" data-testid="quick-reaction">
                      {msg.quick.trim()}
                    </p>
                  )}
                  {msg.content ? (
                    <div className={`${MARKDOWN_CLASSES} ${msg.quick ? 'mt-2' : ''}`} data-testid="answer-text">
                      <ReactMarkdown>{msg.content}</ReactMarkdown>
                    </div>
                  ) : (
                    (!msg.quick || (isStreaming && i === messages.length - 1)) && (
                      <p className={`text-(--coach-muted) ${msg.quick ? 'mt-1' : ''}`} aria-hidden>
                        ...
                      </p>
                    )
                  )}
                  <MessageCards
                    message={msg}
                    boardFen={boardFen}
                    disabled={isStreaming}
                    onBoardActions={onBoardActions}
                    onShowBoard={onShowBoard}
                    onOpenGame={onOpenGame}
                    onSend={onSend}
                    onStartMoments={onStartMoments}
                  />
                </>
              ) : (
                <p className="whitespace-pre-wrap text-[15px] leading-snug">{msg.content}</p>
              )}
              {/* 👍/👎 under a COMPLETED assistant answer (turnId arrives on the
                  final SSE frame) — never on user messages, never while streaming. */}
              {msg.role === 'assistant' && msg.turnId && (
                <FeedbackButtons turnId={msg.turnId} sessionId={sessionId} surface="text" />
              )}
            </div>
          </div>
        ))}

        {messages.length > 0 && !isStreaming && chips.length > 0 && (
          <div className="pl-[38px]">
            <ChipRow prompts={chips} disabled={isStreaming} onSend={onSend} />
          </div>
        )}

        <ToolIndicator toolName={toolActive || ''} visible={!!toolActive} />
      </div>
      {hasUnseen && (
        <button
          type="button"
          onClick={onJumpDown}
          data-testid="new-messages-pill"
          className="absolute bottom-3 left-1/2 min-h-9 -translate-x-1/2 rounded-full border border-(--coach-border) bg-(--coach-surface-2) px-3 text-xs text-(--coach-text) shadow-lg hover:border-(--coach-accent) focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)"
        >
          ↓ {t('newMessages')}
        </button>
      )}
    </div>
  );
}

/**
 * The sheet's peek: the coach's latest line (2–3 lines; tap opens the
 * history), or the greeting on an empty thread.
 */
export function PeekMessage({ messages, onExpand }: { messages: CoachMessage[]; onExpand: () => void }) {
  const t = useTranslations('coach');
  const latest = [...messages].reverse().find((m) => m.role === 'assistant' && messageText(m));
  return (
    <button
      type="button"
      onClick={onExpand}
      data-testid="coach-peek"
      className="flex w-full gap-2.5 rounded-xl text-left focus-visible:outline focus-visible:outline-2 focus-visible:outline-(--coach-accent)"
    >
      <CoachAvatar size={34} />
      <span className="min-w-0 flex-1">
        <span className="mb-0.5 block text-xs font-semibold text-(--coach-muted)">
          {latest ? t('coachJustNow') : t('coachLabel')}
        </span>
        {latest ? (
          // Plain text: markdown's block margins would break the clamp.
          <span className="line-clamp-3 text-[15px] leading-snug text-(--coach-text)">
            {messageText(latest).replace(/[*_`#>]/g, '')}
          </span>
        ) : (
          <>
            <span className="block text-[15px] font-semibold text-(--coach-text)">{t('emptyTitle')}</span>
            <span className="line-clamp-2 text-sm text-(--coach-muted)">{t('emptySubtitle')}</span>
          </>
        )}
      </span>
    </button>
  );
}
