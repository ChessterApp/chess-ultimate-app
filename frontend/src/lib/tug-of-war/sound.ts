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

  /** Correct move: reuse the existing puzzle-solved sample. */
  correctMove(): void {
    if (this.muted || !this.correct) return;
    try {
      this.correct.currentTime = 0;
      void this.correct.play();
    } catch {
      /* autoplay blocked — ignore */
    }
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
