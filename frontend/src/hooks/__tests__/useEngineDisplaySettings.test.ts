/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useEngineDisplaySettings, ENGINE_DISPLAY_STORAGE_KEY } from '../useEngineDisplaySettings';

describe('useEngineDisplaySettings', () => {
  beforeEach(() => {
    window.localStorage.clear();
  });

  it('defaults to depth 18 and 1 line', () => {
    const { result } = renderHook(() => useEngineDisplaySettings());
    expect(result.current.depth).toBe(18);
    expect(result.current.lines).toBe(1);
  });

  it('persists under the new versioned key', () => {
    const { result } = renderHook(() => useEngineDisplaySettings());
    act(() => result.current.setDepth(24));
    act(() => result.current.setLines(3));
    expect(JSON.parse(window.localStorage.getItem(ENGINE_DISPLAY_STORAGE_KEY)!)).toEqual({ depth: 24, lines: 3 });
    expect(result.current).toMatchObject({ depth: 24, lines: 3 });
  });

  it('reads a previously stored value', () => {
    window.localStorage.setItem(ENGINE_DISPLAY_STORAGE_KEY, JSON.stringify({ depth: 12, lines: 5 }));
    const { result } = renderHook(() => useEngineDisplaySettings());
    expect(result.current).toMatchObject({ depth: 12, lines: 5 });
  });

  it('ignores the legacy engineLines / engineDepth keys', () => {
    window.localStorage.setItem('engineLines', '3');
    window.localStorage.setItem('engineDepth', '20');
    const { result } = renderHook(() => useEngineDisplaySettings());
    expect(result.current).toMatchObject({ depth: 18, lines: 1 });
  });

  it('clamps invalid stored values back to defaults', () => {
    window.localStorage.setItem(ENGINE_DISPLAY_STORAGE_KEY, JSON.stringify({ depth: 99, lines: 2 }));
    const a = renderHook(() => useEngineDisplaySettings());
    expect(a.result.current).toMatchObject({ depth: 18, lines: 2 });
    a.unmount();

    window.localStorage.setItem(ENGINE_DISPLAY_STORAGE_KEY, JSON.stringify({ depth: '16', lines: 0 }));
    const b = renderHook(() => useEngineDisplaySettings());
    expect(b.result.current).toMatchObject({ depth: 18, lines: 1 });
    b.unmount();

    window.localStorage.setItem(ENGINE_DISPLAY_STORAGE_KEY, '{not json');
    const c = renderHook(() => useEngineDisplaySettings());
    expect(c.result.current).toMatchObject({ depth: 18, lines: 1 });
    act(() => c.result.current.setLines(7));
    expect(c.result.current.lines).toBe(1);
  });

  it('keeps two mounted instances in sync', () => {
    const a = renderHook(() => useEngineDisplaySettings());
    const b = renderHook(() => useEngineDisplaySettings());
    act(() => a.result.current.setLines(4));
    expect(b.result.current.lines).toBe(4);
    act(() => b.result.current.setDepth(16));
    expect(a.result.current.depth).toBe(16);
  });

  it('picks up changes made in another tab via the storage event', () => {
    const { result } = renderHook(() => useEngineDisplaySettings());
    act(() => {
      window.localStorage.setItem(ENGINE_DISPLAY_STORAGE_KEY, JSON.stringify({ depth: 20, lines: 2 }));
      window.dispatchEvent(new StorageEvent('storage', { key: ENGINE_DISPLAY_STORAGE_KEY }));
    });
    expect(result.current).toMatchObject({ depth: 20, lines: 2 });
  });
});
