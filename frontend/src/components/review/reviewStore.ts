'use client';

import { useReducer } from 'react';
import type { ReviewResult } from './types';

/** One store for the review route: id + data + current ply + sidebar mode. */
export interface ReviewState {
  reviewId: string;
  data: ReviewResult | null;
  currentPly: number;
  mode: 'highlights' | 'review';
}

export type ReviewAction =
  | { type: 'setData'; data: ReviewResult }
  | { type: 'setPly'; ply: number }
  | { type: 'stepPly'; delta: number }
  | { type: 'setMode'; mode: ReviewState['mode'] };

export function reviewReducer(state: ReviewState, action: ReviewAction): ReviewState {
  switch (action.type) {
    case 'setData':
      return { ...state, data: action.data };
    case 'setPly':
      return { ...state, currentPly: clampPly(action.ply, state.data) };
    case 'stepPly':
      return { ...state, currentPly: clampPly(state.currentPly + action.delta, state.data) };
    case 'setMode':
      // Starting the move-by-move review walks the game from the first move.
      return {
        ...state,
        mode: action.mode,
        currentPly: action.mode === 'review' && state.mode !== 'review' ? 0 : state.currentPly,
      };
    default:
      return state;
  }
}

function clampPly(ply: number, data: ReviewResult | null): number {
  const max = data ? data.moves.length : 0;
  return Math.max(0, Math.min(max, ply));
}

export function useReviewStore(reviewId: string) {
  const [state, dispatch] = useReducer(reviewReducer, {
    reviewId,
    data: null,
    currentPly: 0,
    mode: 'highlights',
  });
  return { state, dispatch };
}
