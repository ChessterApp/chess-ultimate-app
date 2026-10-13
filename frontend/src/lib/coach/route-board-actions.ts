/**
 * Routes a turn's board actions: to the study board, to a game tab (by
 * board_id), or to the game against the coach. Pure, so the page stays a thin
 * host and the routing is testable.
 */
import type { BoardAction } from '@/types/coach';
import type { GameStateView } from './boards-api';

/** What a game tab shows besides its position: the coach's arrows and highlights. */
export interface ViewerAnnotations {
  arrows: Array<{ from: string; to: string; brush: string }>;
  highlights: string[];
}

export const EMPTY_ANNOTATIONS: ViewerAnnotations = { arrows: [], highlights: [] };

export interface RoutedBoardActions {
  /** The last game state the coach sent (start_game / make_game_move). */
  game: GameStateView | null;
  /** Actions for the study board. */
  study: BoardAction[];
  /** Actions addressed to a game tab that the tab handles itself, by board id. */
  tabs: Record<string, BoardAction[]>;
  /** The tab the coach last acted on (shown to the student), if any. */
  focusTab: string | null;
}

/** Actions a game tab applies itself; anything else changes the position, which the study board shows. */
const TAB_ACTIONS = new Set<BoardAction['type']>(['navigate', 'draw_arrows', 'highlight_squares']);

export function routeBoardActions(actions: BoardAction[], tabIds: readonly string[]): RoutedBoardActions {
  const out: RoutedBoardActions = { game: null, study: [], tabs: {}, focusTab: null };
  for (const action of actions) {
    if (action.type === 'game') {
      out.game = action.game;
      continue;
    }
    const tab = action.board_id && tabIds.includes(action.board_id) ? action.board_id : null;
    if (tab && TAB_ACTIONS.has(action.type)) {
      (out.tabs[tab] ??= []).push(action);
      out.focusTab = tab;
    } else {
      out.study.push(action);
    }
  }
  return out;
}

export interface ViewerState {
  /** Move index, -1 = the start position. */
  index: number;
  annotations: ViewerAnnotations;
}

/**
 * Apply a tab's actions to its viewer state; `lastIndex` = the game's last move
 * index. The coach's own navigation keeps its arrows (it often moves, then
 * draws); the student stepping through the game clears them (see the page).
 */
export function applyTabActions(state: ViewerState, actions: BoardAction[], lastIndex: number): ViewerState {
  let { index, annotations } = state;
  for (const a of actions) {
    if (a.type === 'navigate') {
      index =
        a.direction === 'first' ? -1
        : a.direction === 'last' ? lastIndex
        : a.direction === 'prev' ? Math.max(-1, index - 1)
        : Math.min(lastIndex, index + 1);
    } else if (a.type === 'draw_arrows') {
      annotations = { ...annotations, arrows: a.arrows };
    } else if (a.type === 'highlight_squares') {
      annotations = { ...annotations, highlights: a.squares };
    }
  }
  return { index, annotations };
}
