import { describe, it, expect, vi, afterEach } from 'vitest';
import { loadMuted, saveMuted, MUTE_STORAGE_KEY, TugSound } from '../sound';

/** Minimal in-memory Storage stand-in for the pure mute helpers. */
function makeStorage(initial: Record<string, string> = {}) {
  const map = new Map(Object.entries(initial));
  return {
    getItem: (k: string) => (map.has(k) ? map.get(k)! : null),
    setItem: (k: string, v: string) => void map.set(k, v),
    removeItem: (k: string) => void map.delete(k),
    get raw() {
      return map;
    },
  };
}

describe('mute persistence', () => {
  it('defaults to unmuted (sound ON) when nothing is stored', () => {
    expect(loadMuted(makeStorage())).toBe(false);
  });

  it('reads a persisted muted flag', () => {
    expect(loadMuted(makeStorage({ [MUTE_STORAGE_KEY]: '1' }))).toBe(true);
  });

  it('treats any non-"1" value as unmuted', () => {
    expect(loadMuted(makeStorage({ [MUTE_STORAGE_KEY]: '0' }))).toBe(false);
    expect(loadMuted(makeStorage({ [MUTE_STORAGE_KEY]: 'true' }))).toBe(false);
  });

  it('saves the muted flag as "1"', () => {
    const s = makeStorage();
    saveMuted(true, s);
    expect(s.raw.get(MUTE_STORAGE_KEY)).toBe('1');
    expect(loadMuted(s)).toBe(true);
  });

  it('removes the key when unmuting', () => {
    const s = makeStorage({ [MUTE_STORAGE_KEY]: '1' });
    saveMuted(false, s);
    expect(s.raw.has(MUTE_STORAGE_KEY)).toBe(false);
    expect(loadMuted(s)).toBe(false);
  });

  it('round-trips a save then load', () => {
    const s = makeStorage();
    saveMuted(true, s);
    expect(loadMuted(s)).toBe(true);
    saveMuted(false, s);
    expect(loadMuted(s)).toBe(false);
  });

  it('is a no-op (returns default) with no storage available', () => {
    // No explicit storage + node env (no window) → graceful default.
    expect(loadMuted()).toBe(false);
    expect(() => saveMuted(true)).not.toThrow();
  });
});

/**
 * The correct-move cue plays an <audio> sample. `HTMLAudioElement.play()`
 * returns a Promise that can reject asynchronously (iOS autoplay
 * NotAllowedError, AbortError from a currentTime reset). If that rejection is
 * left unhandled it bubbles to `window.unhandledrejection` and surfaces as a
 * red "unexpected error" toast — the bug this suite guards against.
 *
 * The test env is `node` (no global `Audio`), so we install a fake so
 * `TugSound` actually builds its audio element and exercises correctMove().
 */
describe('TugSound.correctMove — no unhandled play() rejection', () => {
  let lastAudio: { currentTime: number; preload: string; play: ReturnType<typeof vi.fn> };
  const originalAudio = (globalThis as { Audio?: unknown }).Audio;

  function installFakeAudio() {
    class FakeAudio {
      currentTime = 0;
      preload = '';
      play = vi.fn(() => Promise.resolve());
      constructor(public src: string) {
        lastAudio = this;
      }
    }
    (globalThis as { Audio?: unknown }).Audio = FakeAudio as unknown;
  }

  /** Let queued microtasks + the unhandledRejection check run. */
  const flush = () => new Promise((resolve) => setTimeout(resolve, 10));

  afterEach(() => {
    (globalThis as { Audio?: unknown }).Audio = originalAudio;
    vi.restoreAllMocks();
  });

  it('swallows an async play() rejection (iOS NotAllowedError)', async () => {
    installFakeAudio();
    const sound = new TugSound(false);
    // play() rejects the way iOS does when autoplay is blocked.
    lastAudio.play.mockImplementation(() =>
      Promise.reject(new DOMException('autoplay blocked', 'NotAllowedError')),
    );

    const rejections: unknown[] = [];
    const onUnhandled = (reason: unknown) => rejections.push(reason);
    process.on('unhandledRejection', onUnhandled);
    try {
      expect(() => sound.correctMove()).not.toThrow();
      await flush();
    } finally {
      process.off('unhandledRejection', onUnhandled);
    }

    expect(lastAudio.play).toHaveBeenCalledTimes(1);
    expect(rejections).toEqual([]);
  });

  it('plays the sample once (currentTime reset) when play() resolves', async () => {
    installFakeAudio();
    const sound = new TugSound(false);
    lastAudio.currentTime = 5;

    sound.correctMove();
    await flush();

    expect(lastAudio.play).toHaveBeenCalledTimes(1);
    expect(lastAudio.currentTime).toBe(0);
  });

  it('does not play while muted', async () => {
    installFakeAudio();
    const sound = new TugSound(true);

    sound.correctMove();
    await flush();

    expect(lastAudio.play).not.toHaveBeenCalled();
  });
});
