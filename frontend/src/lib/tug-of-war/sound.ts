/**
 * Tug of War audio.
 *
 * The reducer stays pure — all sound is fired from the component layer on game
 * events. This module holds two things:
 *   1. Pure mute-persistence helpers (unit-tested) — localStorage-backed, with
 *      a graceful no-op when storage is unavailable (SSR / private mode).
 *   2. A tiny client-only player: the correct-move cue reuses the existing
 *      puzzle-solved sample; the wrong-move buzz and the win fanfare are
 *      synthesised with the Web Audio API (no external downloads).
 */

/** localStorage key for the mute preference. */
export const MUTE_STORAGE_KEY = 'tugOfWar.muted';

type StorageLike = Pick<Storage, 'getItem' | 'setItem' | 'removeItem'>;

function resolveStorage(explicit?: StorageLike): StorageLike | null {
  if (explicit) return explicit;
  if (typeof window === 'undefined') return null;
  try {
    return window.localStorage;
  } catch {
    return null;
  }
}

/** Read the persisted mute preference. Default is `false` (sound ON). */
export function loadMuted(storage?: StorageLike): boolean {
  const s = resolveStorage(storage);
  if (!s) return false;
  try {
    return s.getItem(MUTE_STORAGE_KEY) === '1';
  } catch {
    return false;
  }
}

/** Persist the mute preference: `'1'` when muted, key removed when unmuted. */
export function saveMuted(muted: boolean, storage?: StorageLike): void {
  const s = resolveStorage(storage);
  if (!s) return;
  try {
    if (muted) s.setItem(MUTE_STORAGE_KEY, '1');
    else s.removeItem(MUTE_STORAGE_KEY);
  } catch {
    /* storage full / blocked — sound preference is best-effort */
  }
}

/** Path to the reused correct-move sample. */
const CORRECT_SRC = '/sounds/puzzle-solved.mp3';

/**
 * Client-only sound player. Safe to construct during SSR — it feature-detects
 * `Audio`/`AudioContext` and no-ops when they are missing.
 */
export class TugSound {
  private muted: boolean;
  private ctx: AudioContext | null = null;
  private correct: HTMLAudioElement | null = null;
  private correctBuffer: AudioBuffer | null = null;
  private correctBufferPromise: Promise<AudioBuffer | null> | null = null;

  constructor(muted = false) {
    this.muted = muted;
    if (typeof Audio !== 'undefined') {
      this.correct = new Audio(CORRECT_SRC);
      this.correct.preload = 'auto';
    }
  }

  setMuted(muted: boolean): void {
    this.muted = muted;
  }

  /**
   * Prime audio on the first user gesture. iOS/Safari only unlock playback from
   * inside a real pointer/touch/key handler, so MatchScreen calls this on each
   * early interaction until it succeeds. It resumes the shared AudioContext and
   * plays a 1-frame silent buffer inside the gesture — which is what actually
   * unlocks WebKit output — then kicks off decoding the correct-move sample so
   * it is ready by the first solve. Safe to call repeatedly; the decode only
   * runs once.
   *
   * Returns `true` only when the context is `running` afterwards, so the caller
   * knows whether to keep listening for a later gesture (a failed first tap must
   * be retried, not abandoned).
   */
  unlock(): boolean {
    // Declare the iOS audio session so Web Audio ignores the silent switch.
    try {
      const nav = navigator as Navigator & { audioSession?: { type: string } };
      if (nav.audioSession) nav.audioSession.type = 'playback';
    } catch {
      /* not supported — ignore */
    }
    const ctx = this.audioCtx();
    if (!ctx) return false;
    // Play a 1-frame silent buffer inside the gesture to force-unlock WebKit.
    try {
      const buf = ctx.createBuffer(1, 1, 22050);
      const src = ctx.createBufferSource();
      src.buffer = buf;
      src.connect(ctx.destination);
      src.start(0);
    } catch {
      /* createBuffer/start can throw on a closed context — ignore */
    }
    void this.ensureCorrectBuffer(ctx);
    return ctx.state === 'running';
  }

  /** Fetch + decode the correct-move sample once, cached for reuse. */
  private ensureCorrectBuffer(ctx: AudioContext): Promise<AudioBuffer | null> {
    if (this.correctBuffer) return Promise.resolve(this.correctBuffer);
    if (!this.correctBufferPromise) {
      this.correctBufferPromise = fetch(CORRECT_SRC)
        .then((res) => res.arrayBuffer())
        .then((data) => ctx.decodeAudioData(data))
        .then((buffer) => {
          this.correctBuffer = buffer;
          return buffer;
        })
        .catch(() => null);
    }
    return this.correctBufferPromise;
  }

  /** Play a decoded buffer through the shared, already-unlocked context. */
  private playBuffer(ctx: AudioContext, buffer: AudioBuffer): void {
    try {
      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);
      src.start();
    } catch {
      /* buffer source can throw if the context was closed — ignore */
    }
  }

  /** Lazily create / resume the shared AudioContext (needs a user gesture). */
  private audioCtx(): AudioContext | null {
    if (typeof window === 'undefined') return null;
    const AC =
      window.AudioContext ||
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!AC) return null;
    if (!this.ctx) this.ctx = new AC();
    if (this.ctx.state === 'suspended') void this.ctx.resume().catch(() => {});
    return this.ctx;
  }

  /** Play one synthesised tone with a short attack/decay envelope. */
  private tone(freqFrom: number, freqTo: number, at: number, dur: number, type: OscillatorType, peak: number): void {
    const ctx = this.ctx;
    if (!ctx) return;
    const osc = ctx.createOscillator();
    const gain = ctx.createGain();
    osc.type = type;
    osc.frequency.setValueAtTime(freqFrom, at);
    if (freqTo !== freqFrom) osc.frequency.exponentialRampToValueAtTime(freqTo, at + dur);
    gain.gain.setValueAtTime(0.0001, at);
    gain.gain.exponentialRampToValueAtTime(peak, at + 0.015);
    gain.gain.exponentialRampToValueAtTime(0.0001, at + dur);
    osc.connect(gain).connect(ctx.destination);
    osc.start(at);
    osc.stop(at + dur + 0.02);
  }

  /**
   * Correct move: play the puzzle-solved sample through the shared AudioContext
   * so it survives the autoplay policy the same way the wrong/win cues do. Once
   * the context is unlocked (unlock(), on the first gesture) buffer playback
   * works even when the solve resolves from a timer — unlike HTMLAudio.play(),
   * which iOS blocks outside the gesture window and rejects (the old silent-cue
   * bug). Falls back to the <audio> element only when Web Audio is unavailable.
   */
  correctMove(): void {
    if (this.muted) return;
    const ctx = this.audioCtx();
    if (ctx) {
      if (this.correctBuffer) {
        this.playBuffer(ctx, this.correctBuffer);
      } else {
        void this.ensureCorrectBuffer(ctx).then((buffer) => {
          if (buffer) this.playBuffer(ctx, buffer);
        });
      }
      return;
    }
    // No Web Audio (very old browser) — best-effort HTMLAudio fallback. play()
    // can reject asynchronously; swallow it so it never becomes an unhandled
    // rejection (which would surface as a red error toast).
    if (!this.correct) return;
    try {
      this.correct.currentTime = 0;
    } catch {
      /* resetting currentTime can throw on some browsers — ignore */
    }
    this.correct.play()?.catch(() => {});
  }

  /** Wrong move: a short descending buzz/thud. */
  wrongMove(): void {
    if (this.muted) return;
    const ctx = this.audioCtx();
    if (!ctx) return;
    this.tone(170, 70, ctx.currentTime, 0.2, 'sawtooth', 0.22);
  }

  /** Win: a short ascending arpeggio fanfare (C–E–G–C). */
  win(): void {
    if (this.muted) return;
    const ctx = this.audioCtx();
    if (!ctx) return;
    const notes = [523.25, 659.25, 783.99, 1046.5];
    const step = 0.13;
    notes.forEach((freq, i) => {
      this.tone(freq, freq, ctx.currentTime + i * step, 0.3, 'triangle', 0.28);
    });
  }
}
