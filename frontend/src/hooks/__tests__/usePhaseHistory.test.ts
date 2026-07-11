/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach, vi } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { usePhaseHistory } from '../usePhaseHistory';

interface PlayPhase {
  phase: string;
  bot: string | null;
}

const config = (onRestore: (p: PlayPhase, m: { initial: boolean }) => void) => ({
  parse: (params: URLSearchParams): PlayPhase => ({
    phase: params.get('phase') || 'selecting',
    bot: params.get('bot'),
  }),
  serialize: (p: PlayPhase) => ({ phase: p.phase, bot: p.bot }),
  onRestore,
});

describe('usePhaseHistory', () => {
  beforeEach(() => {
    window.history.replaceState(null, '', '/play');
  });

  it('initializes from the current URL on mount (initial: true)', () => {
    window.history.replaceState(null, '', '/play?phase=setup&bot=magnus');
    const onRestore = vi.fn();
    renderHook(() => usePhaseHistory(config(onRestore)));

    expect(onRestore).toHaveBeenCalledTimes(1);
    expect(onRestore).toHaveBeenCalledWith(
      { phase: 'setup', bot: 'magnus' },
      expect.objectContaining({ initial: true }),
    );
  });

  it('defaults to parsed empty params when the URL has none', () => {
    const onRestore = vi.fn();
    renderHook(() => usePhaseHistory(config(onRestore)));

    expect(onRestore).toHaveBeenCalledWith(
      { phase: 'selecting', bot: null },
      expect.objectContaining({ initial: true }),
    );
  });

  it('push adds a history entry with the serialized query params', () => {
    const { result } = renderHook(() => usePhaseHistory(config(vi.fn())));
    const before = window.history.length;

    act(() => result.current.push({ phase: 'setup', bot: 'x' }));

    expect(window.location.search).toBe('?phase=setup&bot=x');
    expect(window.history.length).toBe(before + 1);
  });

  it('push drops empty/null params', () => {
    const { result } = renderHook(() => usePhaseHistory(config(vi.fn())));

    act(() => result.current.push({ phase: 'selecting', bot: null }));

    expect(window.location.search).toBe('?phase=selecting');
  });

  it('replace updates the URL without adding a history entry', () => {
    const { result } = renderHook(() => usePhaseHistory(config(vi.fn())));
    act(() => result.current.push({ phase: 'setup', bot: 'x' }));
    const len = window.history.length;

    act(() => result.current.replace({ phase: 'setup', bot: 'y' }));

    expect(window.location.search).toBe('?phase=setup&bot=y');
    expect(window.history.length).toBe(len);
  });

  it('popstate invokes onRestore with the phase parsed from the URL (initial: false)', () => {
    const onRestore = vi.fn();
    renderHook(() => usePhaseHistory(config(onRestore)));
    onRestore.mockClear();

    act(() => {
      window.history.replaceState(null, '', '/play?phase=playing&bot=z');
      window.dispatchEvent(new PopStateEvent('popstate'));
    });

    expect(onRestore).toHaveBeenCalledWith(
      { phase: 'playing', bot: 'z' },
      expect.objectContaining({ initial: false }),
    );
  });

  it('removes the popstate listener on unmount', () => {
    const onRestore = vi.fn();
    const { unmount } = renderHook(() => usePhaseHistory(config(onRestore)));
    onRestore.mockClear();
    unmount();

    act(() => window.dispatchEvent(new PopStateEvent('popstate')));

    expect(onRestore).not.toHaveBeenCalled();
  });

  it('exposes stable callbacks and does not throw for a bare import (SSR-safe surface)', () => {
    const { result, rerender } = renderHook(() => usePhaseHistory(config(vi.fn())));
    const first = result.current;
    rerender();
    expect(result.current.push).toBe(first.push);
    expect(result.current.replace).toBe(first.replace);
    expect(result.current.back).toBe(first.back);
  });
});
