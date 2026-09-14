// Pure reducer for the wheel config editor. Operates on a segment list; kept
// free of React/DOM so it can be unit-tested directly.

import type { WheelSegment } from './types';
import { MAX_SEGMENTS, MIN_SEGMENTS, makeSegmentId, nextColor } from './presets';

export type EditorAction =
  | { type: 'add' }
  | { type: 'remove'; id: string }
  | { type: 'update'; id: string; patch: Partial<Omit<WheelSegment, 'id'>> }
  | { type: 'move'; id: string; direction: 'up' | 'down' }
  | { type: 'reset'; segments: WheelSegment[] };

export function editorReducer(state: WheelSegment[], action: EditorAction): WheelSegment[] {
  switch (action.type) {
    case 'add': {
      if (state.length >= MAX_SEGMENTS) return state;
      return [
        ...state,
        { id: makeSegmentId(), label: '', color: nextColor(state.length) },
      ];
    }
    case 'remove': {
      if (state.length <= MIN_SEGMENTS) return state;
      return state.filter((s) => s.id !== action.id);
    }
    case 'update': {
      return state.map((s) =>
        s.id === action.id ? { ...s, ...action.patch } : s,
      );
    }
    case 'move': {
      const idx = state.findIndex((s) => s.id === action.id);
      if (idx === -1) return state;
      const target = action.direction === 'up' ? idx - 1 : idx + 1;
      if (target < 0 || target >= state.length) return state;
      const next = [...state];
      [next[idx], next[target]] = [next[target], next[idx]];
      return next;
    }
    case 'reset': {
      return action.segments;
    }
    default:
      return state;
  }
}
