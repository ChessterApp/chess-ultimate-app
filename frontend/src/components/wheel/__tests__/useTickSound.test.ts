/** @vitest-environment jsdom */
import { describe, it, expect, vi, afterEach } from 'vitest';
import { renderHook, cleanup } from '@testing-library/react';
import { useTickSound } from '../useTickSound';

/**
 * Regression: the wheel's tick was silent on iOS/iPad. ensureCtx() only called
 * resume() (un-awaited) and tick() bailed whenever the context wasn't running —
 * WebKit needs a sound started inside the gesture to unlock output, so every
 * tick was dropped. Same bug + fix as tug-of-war's TugSound.unlock().
 */
describe('useTickSound (mobile WebKit unlock)', () => {
  let ctxState: string;
  let resumeCalls: number;
  let primed: number;
  let oscillators: number;

  const PRIMING_BUFFER = { priming: true } as unknown as AudioBuffer;

  function installWebAudio(opts: { resumesToRunning?: boolean } = {}) {
    const resumesToRunning = opts.resumesToRunning ?? true;
    ctxState = 'suspended';
    resumeCalls = 0;
    primed = 0;
    oscillators = 0;
    class FakeCtx {
      destination = {};
      currentTime = 0;
      get state() {
        return ctxState;
      }
      resume = vi.fn(() => {
        resumeCalls += 1;
        if (resumesToRunning) ctxState = 'running';
        return Promise.resolve();
      });
      close = vi.fn(() => Promise.resolve());
      createBuffer = vi.fn(() => PRIMING_BUFFER);
      createBufferSource = vi.fn(() => {
        const node = {
          buffer: null as AudioBuffer | null,
          connect: () => {},
          start: () => {
            if (node.buffer === PRIMING_BUFFER) primed += 1;
          },
        };
        return node;
      });
      createOscillator = vi.fn(() => {
        oscillators += 1;
        return {
          type: 'sine',
          frequency: { setValueAtTime: () => {}, exponentialRampToValueAtTime: () => {} },
          connect: (n: unknown) => n,
          start: () => {},
          stop: () => {},
        };
      });
      createGain = vi.fn(() => ({
        gain: { setValueAtTime: () => {}, exponentialRampToValueAtTime: () => {} },
        connect: (n: unknown) => n,
      }));
    }
    vi.stubGlobal('AudioContext', FakeCtx);
  }

  afterEach(() => {
    cleanup();
    vi.unstubAllGlobals();
    delete (navigator as { audioSession?: unknown }).audioSession;
  });

  it('plays a priming buffer inside the gesture (WebKit force-unlock)', () => {
    installWebAudio();
    const { result } = renderHook(() => useTickSound());
    result.current.ensureCtx();
    expect(primed).toBe(1);
  });

  it('sets navigator.audioSession to playback so the silent switch is ignored', () => {
    installWebAudio();
    const session = { type: 'auto' };
    (navigator as { audioSession?: unknown }).audioSession = session;
    const { result } = renderHook(() => useTickSound());
    result.current.ensureCtx();
    expect(session.type).toBe('playback');
  });

  it('does not throw when navigator.audioSession is absent', () => {
    installWebAudio();
    const { result } = renderHook(() => useTickSound());
    expect(() => result.current.ensureCtx()).not.toThrow();
  });

  it('ensureCtx() reports whether the context is running', () => {
    installWebAudio({ resumesToRunning: false });
    const { result } = renderHook(() => useTickSound());
    expect(result.current.ensureCtx()).toBe(false);
    ctxState = 'running';
    expect(result.current.ensureCtx()).toBe(true);
  });

  it('re-primes on every spin tap so a failed first unlock can recover', () => {
    installWebAudio({ resumesToRunning: false });
    const { result } = renderHook(() => useTickSound());
    result.current.ensureCtx();
    result.current.ensureCtx();
    expect(primed).toBe(2);
  });

  it('tick() plays once the context is running', () => {
    installWebAudio();
    const { result } = renderHook(() => useTickSound());
    result.current.ensureCtx();
    result.current.tick();
    expect(oscillators).toBe(1);
  });

  it('tick() retries resume() instead of silently giving up while suspended', () => {
    installWebAudio({ resumesToRunning: false });
    const { result } = renderHook(() => useTickSound());
    result.current.ensureCtx();
    const before = resumeCalls;
    result.current.tick();
    expect(resumeCalls).toBe(before + 1);
    expect(oscillators).toBe(0); // no queued clicks bursting out later
  });

  it('is a safe no-op without Web Audio (SSR / old browsers)', () => {
    vi.stubGlobal('AudioContext', undefined);
    const { result } = renderHook(() => useTickSound());
    expect(result.current.ensureCtx()).toBe(false);
    expect(() => result.current.tick()).not.toThrow();
  });
});
