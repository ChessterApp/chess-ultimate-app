/**
 * The student's utterance, cut out of the microphone's stream by the page itself (18.11).
 *
 * The voice pipeline used to stream the microphone to Google's transcription model, which said where an
 * utterance ended. With the words going through the coach server instead (Hermes src/voice_stt.py →
 * OpenRouter's transcription, which takes a recording, not a stream), the page decides: speech begins when the
 * level has stayed above the threshold for START_MS, and ends after END_SILENCE_MS without it. What is sent is
 * the speech with PRE_ROLL_MS before it (the first consonant is quieter than the threshold) and the closing
 * silence. Pure: fed with the capture worklet's frames (16 kHz mono 16-bit, each with its RMS), no timers.
 */

export const SAMPLE_RATE = 16000;
/** Loud for this long: speech, not a click. */
export const START_MS = 150;
/** Quiet for this long after speech: the utterance is over. A pause inside a phrase is shorter. */
export const END_SILENCE_MS = 700;
/** Kept before the moment speech was noticed. */
export const PRE_ROLL_MS = 300;
/** Less speech than this in all: a cough or a knock, not sent. */
export const MIN_SPEECH_MS = 250;
/** An utterance is cut at this length whatever the level (a noisy room never goes quiet). */
export const MAX_UTTERANCE_MS = 30000;
/** A frame counts as speech when it is this many times louder than the room's own noise (and above the threshold). */
export const NOISE_FACTOR = 2.5;
/** The room's noise is the quietest stretch of this long: speech has gaps between its words, a fan's hum has none. */
export const NOISE_WINDOW_MS = 5000;
/**
 * The level that is judged is the RMS over this long, not one frame's. The capture hands over frames of 2.7 ms
 * (one audio quantum), and in a real voice single frames fall under any threshold between the pulses of the
 * sound — judged one by one, speech never «stayed» loud for START_MS and no utterance ever began (the app on the
 * emulator with a real microphone, 18.11; the stand's fake microphone plays a file at full level and hid it).
 * A click a few milliseconds long, spread over this window, does not last START_MS.
 */
export const LEVEL_WINDOW_MS = 40;
/** The noise window is kept in steps of this long (their quietest level), not frame by frame. */
const NOISE_STEP_MS = 100;

export interface CutterStep {
  /** Speech has just been noticed (once per utterance). */
  started: boolean;
  /** The utterance that has just ended, ready to send; null while it goes on or when it was too short. */
  utterance: Int16Array | null;
}

const frameMs = (pcm: Int16Array) => (pcm.length / SAMPLE_RATE) * 1000;

function concat(parts: Int16Array[]): Int16Array {
  const out = new Int16Array(parts.reduce((n, p) => n + p.length, 0));
  let at = 0;
  for (const p of parts) {
    out.set(p, at);
    at += p.length;
  }
  return out;
}

export class UtteranceCutter {
  private pre: Int16Array[] = [];
  private preMs = 0;
  private parts: Int16Array[] | null = null;
  private loudMs = 0;
  private quietMs = 0;
  private speechMs = 0;
  private totalMs = 0;
  /** The frames of the last LEVEL_WINDOW_MS (their energy and length): the level judged is their RMS. */
  private recent: { energy: number; ms: number }[] = [];
  private recentMs = 0;
  private recentEnergy = 0;
  /** The quietest level of each past NOISE_STEP_MS, oldest first, NOISE_WINDOW_MS of them: the room's own noise. */
  private steps: number[] = [];
  private stepMin = Infinity;
  private stepMs = 0;

  /** The level now: the RMS of the last LEVEL_WINDOW_MS, this frame included. */
  private level(rms: number, ms: number): number {
    const energy = rms * rms * ms;
    this.recent.push({ energy, ms });
    this.recentMs += ms;
    this.recentEnergy += energy;
    while (this.recent.length > 1 && this.recentMs - this.recent[0].ms >= LEVEL_WINDOW_MS) {
      const old = this.recent.shift()!;
      this.recentMs -= old.ms;
      this.recentEnergy -= old.energy;
    }
    return Math.sqrt(Math.max(0, this.recentEnergy) / this.recentMs);
  }

  /** The room's noise before this frame; 0 until a step has been heard. */
  private noiseFloor(): number {
    let min = this.stepMin;
    for (const l of this.steps) if (l < min) min = l;
    return min === Infinity ? 0 : min;
  }

  private remember(level: number, ms: number): void {
    if (level < this.stepMin) this.stepMin = level;
    this.stepMs += ms;
    if (this.stepMs < NOISE_STEP_MS) return;
    this.steps.push(this.stepMin);
    if (this.steps.length > NOISE_WINDOW_MS / NOISE_STEP_MS) this.steps.shift();
    this.stepMin = Infinity;
    this.stepMs = 0;
  }

  /** True while an utterance is being collected. */
  get speaking(): boolean {
    return this.parts !== null;
  }

  /**
   * One captured frame. *threshold*: the level that counts as speech now — the host raises it while the coach's
   * own voice is playing, as its barge-in does.
   */
  push(pcm: Int16Array, rms: number, threshold: number): CutterStep {
    const ms = frameMs(pcm);
    const level = this.level(rms, ms);
    const loud = level > Math.max(threshold, this.noiseFloor() * NOISE_FACTOR);
    this.remember(level, ms);
    if (this.parts === null) {
      this.pre.push(pcm);
      this.preMs += ms;
      while (this.pre.length > 1 && this.preMs - frameMs(this.pre[0]) >= PRE_ROLL_MS + this.loudMs + (loud ? ms : 0)) {
        this.preMs -= frameMs(this.pre.shift()!);
      }
      if (!loud) {
        this.loudMs = 0;
        return { started: false, utterance: null };
      }
      this.loudMs += ms;
      if (this.loudMs < START_MS) return { started: false, utterance: null };
      this.parts = this.pre;
      this.totalMs = this.preMs;
      this.speechMs = this.loudMs;
      this.quietMs = 0;
      this.pre = [];
      this.preMs = 0;
      this.loudMs = 0;
      return { started: true, utterance: null };
    }
    this.parts.push(pcm);
    this.totalMs += ms;
    if (loud) {
      this.quietMs = 0;
      this.speechMs += ms;
    } else {
      this.quietMs += ms;
    }
    if (this.quietMs < END_SILENCE_MS && this.totalMs < MAX_UTTERANCE_MS) return { started: false, utterance: null };
    const utterance = this.speechMs >= MIN_SPEECH_MS ? concat(this.parts) : null;
    this.reset();
    return { started: false, utterance };
  }

  /** Drop what is being collected (the microphone stops, the coach starts over). The room's noise is kept. */
  reset(): void {
    this.pre = [];
    this.preMs = 0;
    this.parts = null;
    this.loudMs = 0;
    this.quietMs = 0;
    this.speechMs = 0;
    this.totalMs = 0;
  }
}

/** *pcm* (mono, 16-bit) as a WAV file's bytes — the container every recogniser reads. */
export function wavBytes(pcm: Int16Array, rate: number = SAMPLE_RATE): Uint8Array<ArrayBuffer> {
  const data = pcm.length * 2;
  const out = new Uint8Array(new ArrayBuffer(44 + data));
  const view = new DataView(out.buffer);
  const tag = (at: number, s: string) => { for (let i = 0; i < s.length; i++) view.setUint8(at + i, s.charCodeAt(i)); };
  tag(0, 'RIFF');
  view.setUint32(4, 36 + data, true);
  tag(8, 'WAVE');
  tag(12, 'fmt ');
  view.setUint32(16, 16, true);
  view.setUint16(20, 1, true);          // PCM
  view.setUint16(22, 1, true);          // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * 2, true);   // bytes a second
  view.setUint16(32, 2, true);          // bytes a sample
  view.setUint16(34, 16, true);         // bits a sample
  tag(36, 'data');
  view.setUint32(40, data, true);
  for (let i = 0; i < pcm.length; i++) view.setInt16(44 + i * 2, pcm[i], true);
  return out;
}
