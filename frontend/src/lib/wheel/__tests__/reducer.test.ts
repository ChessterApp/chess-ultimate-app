import { describe, it, expect } from 'vitest';
import { editorReducer } from '../reducer';
import type { WheelSegment } from '../types';
import { MAX_SEGMENTS, MIN_SEGMENTS } from '../presets';

function seg(id: string, label = id): WheelSegment {
  return { id, label, color: '#c62828' };
}

function makeMany(n: number): WheelSegment[] {
  return Array.from({ length: n }, (_, i) => seg(`s${i}`));
}

describe('editorReducer', () => {
  it('add appends a new segment', () => {
    const next = editorReducer([seg('a'), seg('b')], { type: 'add' });
    expect(next).toHaveLength(3);
    expect(next[2].label).toBe('');
  });

  it('add is capped at MAX_SEGMENTS', () => {
    const full = makeMany(MAX_SEGMENTS);
    expect(editorReducer(full, { type: 'add' })).toBe(full);
  });

  it('remove deletes by id', () => {
    const next = editorReducer([seg('a'), seg('b'), seg('c')], { type: 'remove', id: 'b' });
    expect(next.map((s) => s.id)).toEqual(['a', 'c']);
  });

  it('remove refuses to go below MIN_SEGMENTS', () => {
    const min = makeMany(MIN_SEGMENTS);
    expect(editorReducer(min, { type: 'remove', id: 's0' })).toBe(min);
  });

  it('update patches only the target segment', () => {
    const next = editorReducer([seg('a'), seg('b')], {
      type: 'update',
      id: 'a',
      patch: { label: 'Приз', emoji: '🎁' },
    });
    expect(next[0]).toMatchObject({ id: 'a', label: 'Приз', emoji: '🎁' });
    expect(next[1]).toEqual(seg('b'));
  });

  it('move up swaps with the previous segment', () => {
    const next = editorReducer([seg('a'), seg('b'), seg('c')], {
      type: 'move',
      id: 'b',
      direction: 'up',
    });
    expect(next.map((s) => s.id)).toEqual(['b', 'a', 'c']);
  });

  it('move down swaps with the next segment', () => {
    const next = editorReducer([seg('a'), seg('b'), seg('c')], {
      type: 'move',
      id: 'b',
      direction: 'down',
    });
    expect(next.map((s) => s.id)).toEqual(['a', 'c', 'b']);
  });

  it('move is a no-op at the boundaries', () => {
    const state = [seg('a'), seg('b')];
    expect(editorReducer(state, { type: 'move', id: 'a', direction: 'up' })).toBe(state);
    expect(editorReducer(state, { type: 'move', id: 'b', direction: 'down' })).toBe(state);
  });

  it('reset replaces the whole list', () => {
    const replacement = [seg('x'), seg('y')];
    expect(editorReducer([seg('a')], { type: 'reset', segments: replacement })).toBe(replacement);
  });

  it('does not mutate the input state', () => {
    const state = [seg('a'), seg('b')];
    const snapshot = JSON.parse(JSON.stringify(state));
    editorReducer(state, { type: 'add' });
    editorReducer(state, { type: 'move', id: 'a', direction: 'down' });
    expect(state).toEqual(snapshot);
  });
});
