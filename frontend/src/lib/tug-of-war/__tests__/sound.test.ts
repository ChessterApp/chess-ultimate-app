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

/**
 * When Web Audio is available (the real browser case), the correct-move cue is
 * routed through the shared AudioContext — the same unlock domain as the
 * wrong/win cues — instead of HTMLAudio.play(). This is what makes it audible
 * on iOS after the opponent-reply timer resolves the solve outside the gesture
 * window (the "no sound anymore" regression). unlock() resumes the context from
 * the first gesture; correctMove() then plays a decoded buffer.
 */
describe('TugSound.correctMove — Web Audio path', () => {
  const originalWindow = (globalThis as { window?: unknown }).window;
  const originalFetch = (globalThis as { fetch?: unknown }).fetch;
  const originalAudio = (globalThis as { Audio?: unknown }).Audio;

  let resumeCalls: number;
  let started: number;
  let primed: number;
  let ctxState: string;

  /** A sentinel returned by createBuffer so the priming node is distinguishable. */
  const PRIMING_BUFFER = { priming: true } as unknown as AudioBuffer;

  function installWebAudio(
    decode?: () => Promise<AudioBuffer>,
    opts: { resumesToRunning?: boolean } = {},
  ) {
    const resumesToRunning = opts.resumesToRunning ?? true;
    resumeCalls = 0;
    started = 0;
    primed = 0;
    ctxState = 'suspended';
    class FakeCtx {
      destination = {};
      get state() {
        return ctxState;
      }
      resume = vi.fn(() => {
        if (resumesToRunning) ctxState = 'running';
        resumeCalls += 1;
        return Promise.resolve();
      });
      decodeAudioData = vi.fn(
        decode ?? (() => Promise.resolve({} as AudioBuffer)),
      );
      createBuffer = vi.fn(() => PRIMING_BUFFER);
      createBufferSource = vi.fn(() => {
        const node = {
          buffer: null as AudioBuffer | null,
          connect: () => {},
          start: () => {
            // The priming node plays the createBuffer sentinel; cue nodes play a
            // decoded buffer. Count them separately so `started` tracks cues only.
            if (node.buffer === PRIMING_BUFFER) primed += 1;
            else started += 1;
          },
        };
        return node;
      });
      // Minimal oscillator/gain graph so the synth cues (wrong/win) don't throw.
      createOscillator = vi.fn(() => ({
        type: 'sine',
        frequency: { setValueAtTime: () => {}, exponentialRampToValueAtTime: () => {} },
        connect: (n: unknown) => n,
        start: () => {},
        stop: () => {},
      }));
      createGain = vi.fn(() => ({
        gain: { setValueAtTime: () => {}, exponentialRampToValueAtTime: () => {} },
        connect: (n: unknown) => n,
      }));
      currentTime = 0;
    }
    (globalThis as { window?: unknown }).window = { AudioContext: FakeCtx };
    (globalThis as { fetch?: unknown }).fetch = vi.fn(() =>
      Promise.resolve({ arrayBuffer: () => Promise.resolve(new ArrayBuffer(8)) }),
    );
  }

  const flush = () => new Promise((resolve) => setTimeout(resolve, 10));

  afterEach(() => {
    (globalThis as { window?: unknown }).window = originalWindow;
    (globalThis as { fetch?: unknown }).fetch = originalFetch;
    (globalThis as { Audio?: unknown }).Audio = originalAudio;
    vi.unstubAllGlobals();
    vi.restoreAllMocks();
  });

  it('unlock() resumes the AudioContext (first-gesture unlock)', async () => {
    installWebAudio();
    const sound = new TugSound(false);
    sound.unlock();
    await flush();
    expect(resumeCalls).toBeGreaterThan(0);
    expect(ctxState).toBe('running');
  });

  it('correctMove plays a decoded buffer through the context', async () => {
    installWebAudio();
    const sound = new TugSound(false);
    sound.unlock(); // decode the buffer up front
    await flush();
    sound.correctMove();
    await flush();
    expect(started).toBe(1);
  });

  it('plays even when correctMove runs before unlock (lazy decode)', async () => {
    installWebAudio();
    const sound = new TugSound(false);
    sound.correctMove();
    await flush();
    expect(started).toBe(1);
  });

  it('does not play while muted', async () => {
    installWebAudio();
    const sound = new TugSound(true);
    sound.unlock();
    await flush();
    sound.correctMove();
    await flush();
    expect(started).toBe(0);
  });

  it('swallows a decode failure without an unhandled rejection', async () => {
    installWebAudio(() => Promise.reject(new Error('decode failed')));
    const sound = new TugSound(false);
    const rejections: unknown[] = [];
    const onUnhandled = (reason: unknown) => rejections.push(reason);
    process.on('unhandledRejection', onUnhandled);
    try {
      sound.unlock();
      sound.correctMove();
      await flush();
    } finally {
      process.off('unhandledRejection', onUnhandled);
    }
    expect(rejections).toEqual([]);
    expect(started).toBe(0);
  });

  it('plays a priming buffer on unlock() (WebKit output force-unlock)', async () => {
    installWebAudio();
    const sound = new TugSound(false);
    sound.unlock();
    await flush();
    expect(primed).toBe(1);
  });

  it('sets navigator.audioSession.type = "playback" when the API exists', () => {
    installWebAudio();
    const audioSession = { type: 'auto' };
    vi.stubGlobal('navigator', { audioSession });
    const sound = new TugSound(false);
    sound.unlock();
    expect(audioSession.type).toBe('playback');
  });

  it('does not throw on unlock() when navigator.audioSession is absent', () => {
    installWebAudio();
    vi.stubGlobal('navigator', {});
    const sound = new TugSound(false);
    expect(() => sound.unlock()).not.toThrow();
  });

  it('unlock() returns true when the context ends up running', () => {
    installWebAudio();
    const sound = new TugSound(false);
    expect(sound.unlock()).toBe(true);
    expect(ctxState).toBe('running');
  });

  it('unlock() returns false when the context stays suspended', () => {
    installWebAudio(undefined, { resumesToRunning: false });
    const sound = new TugSound(false);
    expect(sound.unlock()).toBe(false);
    expect(ctxState).toBe('suspended');
  });

  it('cue methods still attempt resume() when the context is suspended', () => {
    installWebAudio(undefined, { resumesToRunning: false });
    const sound = new TugSound(false);
    sound.unlock(); // one resume attempt
    const afterUnlock = resumeCalls;
    sound.wrongMove();
    sound.win();
    sound.correctMove();
    expect(resumeCalls).toBeGreaterThan(afterUnlock);
  });
});
