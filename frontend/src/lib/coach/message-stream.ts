/**
 * One streamed SSE frame of a coach turn applied to its assistant message.
 *
 * Hermes may answer in two parts: `{"stage":"quick"}`, the quick reaction's
 * deltas, a "\n\n" delta, `{"stage":"answer"}`, then the full answer's deltas.
 * The reaction goes to `quick` and the answer to `content`, so the reaction
 * stays its own short line above the answer as it streams. A turn without
 * stages streams into `content` exactly as before.
 */

import type { BoardAction, CoachMessage, GameResult } from '@/types/coach';
import { parseToolSummary } from './tool-summary';

export interface StreamFrame {
  delta?: string;
  stage?: string;
  tool_result?: { tool?: string; ok?: boolean; summary?: unknown };
  board_actions?: BoardAction[];
  game_results?: GameResult[];
  done?: boolean;
  turn_id?: string;
}

export function applyStreamFrame(msg: CoachMessage, frame: StreamFrame): CoachMessage {
  let next = msg;
  if (frame.stage === 'quick') {
    next = { ...next, stage: 'quick', quick: next.quick ?? '' };
  } else if (frame.stage === 'answer') {
    next = { ...next, stage: 'answer', quick: (next.quick ?? '').trim() };
  }
  if (typeof frame.delta === 'string' && frame.delta) {
    next =
      next.stage === 'quick'
        ? { ...next, quick: (next.quick ?? '') + frame.delta }
        : { ...next, content: next.content + frame.delta };
  }
  if (frame.tool_result) {
    const summary = parseToolSummary(frame.tool_result.summary);
    if (summary) next = { ...next, summaries: [...(next.summaries ?? []), summary] };
  }
  if (Array.isArray(frame.board_actions) && frame.board_actions.length) {
    // A turn may send several board frames (a tool's position, then inline arrows): keep them all.
    next = { ...next, boardActions: [...(next.boardActions ?? []), ...frame.board_actions] };
  }
  if (Array.isArray(frame.game_results)) {
    next = { ...next, gameResults: frame.game_results };
  }
  if (frame.done && frame.turn_id) {
    next = { ...next, turnId: frame.turn_id };
  }
  return next;
}

/** What the message says, as one plain string (the peek line, the play strip's bubble). */
export function messageText(msg: Pick<CoachMessage, 'content' | 'quick'>): string {
  return [msg.quick?.trim(), msg.content.trim()].filter(Boolean).join('\n\n');
}
