import { describe, expect, it } from 'vitest';
import {
  EARLY_SILENCE_MS, END_SILENCE_MS, MAX_UTTERANCE_MS, MIN_SPEECH_MS, PRE_ROLL_MS, SAMPLE_RATE, START_MS, UtteranceCutter, wavBytes,
} from '../voice-utterance';

/** 18.11: the page cuts the student's utterance itself — the words go through the coach server and OpenRouter,
 *  which take a recording, not a stream (the Google project that heard the stream ran out of credit). */

const FRAME_MS = 20;
const THRESHOLD = 0.02;
const frame = (value: number) => new Int16Array((SAMPLE_RATE * FRAME_MS) / 1000).fill(value);
const QUIET = { pcm: () => frame(1), rms: 0.003 };
const LOUD = { pcm: () => frame(900), rms: 0.08 };

/** Feed *ms* of one level; the steps that reported something. */
function feed(cutter: UtteranceCutter, level: { pcm: () => Int16Array; rms: number }, ms: number, threshold = THRESHOLD) {
  const out = [];
  for (let t = 0; t < ms; t += FRAME_MS) {
    const step = cutter.push(level.pcm(), level.rms, threshold);
    if (step.started || step.utterance) out.push(step);
  }
  return out;
}
const lengthMs = (pcm: Int16Array) => (pcm.length / SAMPLE_RATE) * 1000;

describe('the utterance cut out of the microphone', () => {
  it('begins after sustained speech and ends after the closing silence, with the lead-in kept', () => {
    const cutter = new UtteranceCutter();
    expect(feed(cutter, QUIET, 1000)).toEqual([]);
    const started = feed(cutter, LOUD, 1200);
    expect(started).toHaveLength(1);
    expect(started[0].started).toBe(true);
    expect(cutter.speaking).toBe(true);
    const ended = feed(cutter, QUIET, END_SILENCE_MS + 100);
    expect(ended).toHaveLength(1);
    const utterance = ended[0].utterance!;
    // The speech, the lead-in before it and the closing silence — and nothing of the second of quiet before.
    expect(lengthMs(utterance)).toBeGreaterThanOrEqual(1200 + PRE_ROLL_MS + END_SILENCE_MS - FRAME_MS);
    expect(lengthMs(utterance)).toBeLessThanOrEqual(1200 + PRE_ROLL_MS + END_SILENCE_MS + 2 * FRAME_MS);
    expect(cutter.speaking).toBe(false);
  });

  it('keeps a pause inside the phrase', () => {
    const cutter = new UtteranceCutter();
    feed(cutter, QUIET, 400);
    feed(cutter, LOUD, 600);
    expect(feed(cutter, QUIET, END_SILENCE_MS - 200)).toEqual([]);   // «конь… эф три»
    feed(cutter, LOUD, 600);
    const ended = feed(cutter, QUIET, END_SILENCE_MS + 60);
    expect(ended).toHaveLength(1);
    expect(lengthMs(ended[0].utterance!)).toBeGreaterThan(600 + (END_SILENCE_MS - 200) + 600);
  });

  it('takes a click or a cough for nothing', () => {
    const cutter = new UtteranceCutter();
    feed(cutter, QUIET, 400);
    // Too short to be speech at all (the level is judged over 40 ms, so a burst lasts that much longer).
    expect(feed(cutter, LOUD, START_MS - 3 * FRAME_MS)).toEqual([]);
    expect(feed(cutter, QUIET, 400)).toEqual([]);
    expect(cutter.speaking).toBe(false);
    expect(feed(cutter, LOUD, START_MS)).toHaveLength(1);           // noticed…
    expect(cutter.speaking).toBe(true);
    expect(feed(cutter, QUIET, END_SILENCE_MS + 60)).toEqual([]);    // …but less than MIN_SPEECH_MS of it: not sent
    expect(cutter.speaking).toBe(false);
    expect(START_MS).toBeLessThan(MIN_SPEECH_MS);
  });

  it('cuts an utterance that never ends', () => {
    // Words with the short gaps between them, for longer than any phrase said to a coach.
    const cutter = new UtteranceCutter();
    const done = [];
    for (let t = 0; t < MAX_UTTERANCE_MS + 2000; t += 500) {
      done.push(...feed(cutter, LOUD, 400).filter((s) => s.utterance), ...feed(cutter, QUIET, 100).filter((s) => s.utterance));
    }
    expect(done).toHaveLength(1);
    expect(lengthMs(done[0].utterance!)).toBeLessThanOrEqual(MAX_UTTERANCE_MS + FRAME_MS);
    expect(lengthMs(done[0].utterance!)).toBeGreaterThan(MAX_UTTERANCE_MS - 1000);
  });

  it('follows the room: a steady hum is not speech, a voice over it is', () => {
    const cutter = new UtteranceCutter();
    const HUM = { pcm: () => frame(300), rms: 0.03 };                // above the fixed threshold, but it is the room
    expect(feed(cutter, HUM, 6000)).toEqual([]);
    expect(cutter.speaking).toBe(false);
    const VOICE = { pcm: () => frame(2000), rms: 0.15 };
    expect(feed(cutter, VOICE, 500).some((s) => s.started)).toBe(true);
  });

  it('hears only a raised voice while the coach is talking', () => {
    const cutter = new UtteranceCutter();
    feed(cutter, QUIET, 400);
    const ECHO = { pcm: () => frame(400), rms: 0.035 };              // the coach's own voice in the microphone
    expect(feed(cutter, ECHO, 1500, 0.05)).toEqual([]);              // the host's threshold while it plays
    expect(feed(cutter, LOUD, 400, 0.05).some((s) => s.started)).toBe(true);
  });

  it('hears a real voice: frames of one audio quantum, every other one under the threshold', () => {
    // The capture's frames are 128 samples of 48 kHz — 2.7 ms — and between the pulses of a voice single frames
    // are quiet. Judged frame by frame, the speech never lasted START_MS (the emulator's real microphone, 18.11).
    const cutter = new UtteranceCutter();
    const quantum = (value: number) => new Int16Array(43).fill(value);
    const steps = [];
    const say = (ms: number, levels: number[]) => {
      for (let t = 0, i = 0; t < ms; t += 43 / 16, i++) {
        const rms = levels[i % levels.length];
        const step = cutter.push(quantum(rms > 0.02 ? 900 : 1), rms, THRESHOLD);
        if (step.started || step.utterance) steps.push(step);
      }
    };
    say(500, [0.003]);
    say(1500, [0.09, 0.012, 0.07, 0.008, 0.11, 0.015]);   // a voice at an ordinary level: half its frames «quiet»
    expect(steps.map((s) => s.started)).toEqual([true]);
    say(END_SILENCE_MS + 100, [0.003]);
    expect(steps).toHaveLength(2);
    expect(lengthMs(steps[1].utterance!)).toBeGreaterThan(1500 + END_SILENCE_MS - 100);
  });

  it('does not take one loud frame for speech', () => {
    const cutter = new UtteranceCutter();
    const quantum = (value: number) => new Int16Array(43).fill(value);
    const out = [];
    for (let i = 0; i < 400; i++) out.push(cutter.push(quantum(1), 0.003, THRESHOLD));
    out.push(cutter.push(quantum(20000), 0.6, THRESHOLD), cutter.push(quantum(20000), 0.6, THRESHOLD));   // a knock: 5 ms
    for (let i = 0; i < 400; i++) out.push(cutter.push(quantum(1), 0.003, THRESHOLD));
    expect(out.some((s) => s.started || s.utterance)).toBe(false);
  });

  it('starts over on reset', () => {
    const cutter = new UtteranceCutter();
    feed(cutter, QUIET, 200);
    feed(cutter, LOUD, 600);
    cutter.reset();
    expect(cutter.speaking).toBe(false);
    expect(feed(cutter, QUIET, END_SILENCE_MS + 100)).toEqual([]);
  });
});

describe('wavBytes', () => {
  it('writes a 16 kHz mono 16-bit WAV', () => {
    const pcm = new Int16Array([0, 1, -1, 32767, -32768]);
    const wav = wavBytes(pcm);
    const view = new DataView(wav.buffer);
    const text = (at: number, n: number) => String.fromCharCode(...wav.subarray(at, at + n));
    expect(wav.length).toBe(44 + pcm.length * 2);
    expect([text(0, 4), text(8, 4), text(12, 4), text(36, 4)]).toEqual(['RIFF', 'WAVE', 'fmt ', 'data']);
    expect(view.getUint32(4, true)).toBe(36 + pcm.length * 2);
    expect([view.getUint16(20, true), view.getUint16(22, true), view.getUint32(24, true), view.getUint16(34, true)]).toEqual([1, 1, 16000, 16]);
    expect(view.getUint32(40, true)).toBe(pcm.length * 2);
    expect([0, 1, 2, 3, 4].map((i) => view.getInt16(44 + i * 2, true))).toEqual([0, 1, -1, 32767, -32768]);
  });
});

describe('the early send (20.11): the phrase goes to be heard after a short quiet', () => {
  const steps = (cutter: UtteranceCutter, level: { pcm: () => Int16Array; rms: number }, ms: number) => {
    const out = [];
    for (let t = 0; t < ms; t += FRAME_MS) out.push(cutter.push(level.pcm(), level.rms, THRESHOLD));
    return out.filter((s) => s.started || s.utterance || s.early);
  };
  it('once, after EARLY_SILENCE_MS; the utterance at the end names it as the same phrase', () => {
    const cutter = new UtteranceCutter();
    steps(cutter, QUIET, 300);
    steps(cutter, LOUD, 1000);
    const quiet = steps(cutter, QUIET, END_SILENCE_MS + 60);
    const early = quiet.filter((s) => s.early);
    const end = quiet.find((s) => s.utterance)!;
    expect(early).toHaveLength(1);
    expect(end.sameAsEarly).toBe(early[0].early!.id);
    expect(lengthMs(early[0].early!.pcm)).toBeGreaterThanOrEqual(1000 + EARLY_SILENCE_MS - FRAME_MS);
  });
  it('speech after it: the early send is not the phrase, a new one comes after the next quiet', () => {
    const cutter = new UtteranceCutter();
    steps(cutter, QUIET, 300);
    steps(cutter, LOUD, 800);
    const first = steps(cutter, QUIET, EARLY_SILENCE_MS + 100).find((s) => s.early)!;
    steps(cutter, LOUD, 800);
    const quiet = steps(cutter, QUIET, END_SILENCE_MS + 60);
    const second = quiet.find((s) => s.early)!;
    const end = quiet.find((s) => s.utterance)!;
    expect(second.early!.id).not.toBe(first.early!.id);
    expect(end.sameAsEarly).toBe(second.early!.id);
  });
  it('a cough sends nothing ahead', () => {
    const cutter = new UtteranceCutter();
    steps(cutter, QUIET, 300);
    steps(cutter, LOUD, START_MS);
    expect(steps(cutter, QUIET, END_SILENCE_MS + 60).some((s) => s.early)).toBe(false);
  });
});
