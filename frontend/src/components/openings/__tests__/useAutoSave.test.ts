// @vitest-environment jsdom
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useAutoSave, type AutoSaveEntry } from '../useAutoSave';

interface Props {
  scope: string | null;
  entry: AutoSaveEntry<string> | null;
}

const entry = (value: string): AutoSaveEntry<string> => ({ key: value, value });

function deferred() {
  let resolve!: (ok: boolean) => void;
  const promise = new Promise<boolean>(r => { resolve = r; });
  return { promise, resolve };
}

function setup(save: (v: string) => Promise<boolean>, initial: Props = { scope: 'g1', entry: null }) {
  const onClean = vi.fn();
  const hook = renderHook((p: Props) => useAutoSave({ ...p, save, onClean, delayMs: 1500 }), { initialProps: initial });
  return { ...hook, onClean };
}

beforeEach(() => vi.useFakeTimers());
afterEach(() => vi.useRealTimers());

describe('useAutoSave', () => {
  it('coalesces rapid edits into one debounced save', async () => {
    const save = vi.fn().mockResolvedValue(true);
    const { rerender, result, onClean } = setup(save);
    rerender({ scope: 'g1', entry: entry('1. e4') });
    await act(() => vi.advanceTimersByTimeAsync(500));
    rerender({ scope: 'g1', entry: entry('1. e4 e5') });
    await act(() => vi.advanceTimersByTimeAsync(500));
    rerender({ scope: 'g1', entry: entry('1. e4 e5 2. Nf3') });
    expect(save).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(1500));
    expect(save).toHaveBeenCalledTimes(1);
    expect(save).toHaveBeenCalledWith('1. e4 e5 2. Nf3');
    expect(onClean).toHaveBeenCalledWith('1. e4 e5 2. Nf3');
    expect(result.current.status).toBe('saved');
  });

  it('flush saves immediately', async () => {
    const save = vi.fn().mockResolvedValue(true);
    const { rerender, result } = setup(save);
    rerender({ scope: 'g1', entry: entry('1. d4') });
    let ok = false;
    await act(async () => { ok = await result.current.flush(); });
    expect(ok).toBe(true);
    expect(save).toHaveBeenCalledWith('1. d4');
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('reports a failure as error and Retry saves again', async () => {
    const save = vi.fn().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    const { rerender, result, onClean } = setup(save);
    rerender({ scope: 'g1', entry: entry('1. c4') });
    await act(() => vi.advanceTimersByTimeAsync(1500));
    expect(result.current.status).toBe('error');
    expect(result.current.hasUnsaved()).toBe(true);
    expect(onClean).not.toHaveBeenCalled();
    await act(async () => { await result.current.flush(); });
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith('1. c4');
    expect(result.current.status).toBe('saved');
    expect(result.current.hasUnsaved()).toBe(false);
  });

  it('saves an edit made during an in-flight save afterwards, without marking clean early', async () => {
    const first = deferred();
    const save = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(true);
    const { rerender, result, onClean } = setup(save);
    rerender({ scope: 'g1', entry: entry('1. e4') });
    await act(() => vi.advanceTimersByTimeAsync(1500));
    expect(result.current.status).toBe('saving');
    rerender({ scope: 'g1', entry: entry('1. e4 c5') });
    await act(async () => { first.resolve(true); });
    // Tree changed since the first save started: stays dirty.
    expect(onClean).not.toHaveBeenCalled();
    await act(() => vi.advanceTimersByTimeAsync(1500));
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith('1. e4 c5');
    expect(onClean).toHaveBeenCalledTimes(1);
    expect(onClean).toHaveBeenCalledWith('1. e4 c5');
  });

  it('runs saves one at a time', async () => {
    const first = deferred();
    const save = vi.fn().mockReturnValueOnce(first.promise).mockResolvedValue(true);
    const { rerender, result } = setup(save);
    rerender({ scope: 'g1', entry: entry('a') });
    act(() => { result.current.flush(); });
    rerender({ scope: 'g1', entry: entry('b') });
    act(() => { result.current.flush(); });
    await act(async () => {});
    expect(save).toHaveBeenCalledTimes(1);
    await act(async () => { first.resolve(true); });
    expect(save).toHaveBeenCalledTimes(2);
  });

  it('flushes the previous scope immediately when the scope changes', async () => {
    const save = vi.fn().mockResolvedValue(true);
    const { rerender } = setup(save);
    rerender({ scope: 'g1', entry: entry('1. e4') });
    rerender({ scope: 'g2', entry: null });
    await act(async () => {});
    expect(save).toHaveBeenCalledWith('1. e4');
  });

  it('drops a pending save when the same document becomes clean', async () => {
    const save = vi.fn().mockResolvedValue(true);
    const { rerender } = setup(save);
    rerender({ scope: 'g1', entry: entry('1. e4') });
    rerender({ scope: 'g1', entry: null });
    await act(() => vi.advanceTimersByTimeAsync(2000));
    expect(save).not.toHaveBeenCalled();
  });

  it('discard forgets pending and failed saves', async () => {
    const save = vi.fn().mockResolvedValue(false);
    const { rerender, result } = setup(save);
    rerender({ scope: 'g1', entry: entry('1. e4') });
    await act(() => vi.advanceTimersByTimeAsync(1500));
    rerender({ scope: 'g1', entry: entry('1. e4 e5') });
    act(() => result.current.discard());
    expect(result.current.status).toBe('idle');
    expect(result.current.hasUnsaved()).toBe(false);
    await act(async () => { await result.current.flush(); });
    expect(save).toHaveBeenCalledTimes(1);
  });

  it('flushes when the page is hidden and on unmount', async () => {
    const save = vi.fn().mockResolvedValue(true);
    const { rerender, unmount } = setup(save);
    rerender({ scope: 'g1', entry: entry('1. e4') });
    vi.spyOn(document, 'visibilityState', 'get').mockReturnValue('hidden');
    await act(async () => { document.dispatchEvent(new Event('visibilitychange')); });
    expect(save).toHaveBeenCalledTimes(1);
    rerender({ scope: 'g1', entry: entry('1. e4 e5') });
    unmount();
    await act(async () => {});
    expect(save).toHaveBeenCalledTimes(2);
    expect(save).toHaveBeenLastCalledWith('1. e4 e5');
  });

  it('warns before unload only while something is unsaved', async () => {
    const save = vi.fn().mockResolvedValue(true);
    const { rerender } = setup(save);
    const clean = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(clean);
    expect(clean.defaultPrevented).toBe(false);

    rerender({ scope: 'g1', entry: entry('1. e4') });
    const dirty = new Event('beforeunload', { cancelable: true });
    window.dispatchEvent(dirty);
    expect(dirty.defaultPrevented).toBe(true);
  });
});
