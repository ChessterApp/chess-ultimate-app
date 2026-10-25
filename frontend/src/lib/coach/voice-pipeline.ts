/**
 * The voice pipeline (prototype, 2026-10-25): speech → transcript → the TEXT coach → speech.
 *
 * Alexander's proposal: one brain for everything. The student's words go through Google's
 * transcription-only Live model, the text goes to the ordinary text turn (`/api/coach/chat`, with
 * every server-side mechanism: pre-steps, the board, the answer check that withholds wrong
 * sentences), and the streamed answer is read aloud sentence by sentence by Google's TTS. No second
 * model talks to the student, so nothing is said that the server did not verify, and the board is
 * moved by the server, never by a model's tool call. Pure helpers here; the hook is
 * src/hooks/usePipelineVoice.ts.
 */

export const STT_STABLE_MS = 350;      // a transcript unchanged this long after speech ended is final…
export const STT_STABLE_SLOW_MS = 900;  // …or this long when it has no terminal punctuation
export const SILENCE_MS = 400;         // no speech energy for this long before an utterance may close

/** The text a sentence is read from: markdown and board markup stripped, whitespace collapsed. */
export function speakable(text: string): string {
  return text
    .replace(/\[\[[^\]]*\]\]/g, ' ')                  // [[arrows: …]] left by the stream
    .replace(/!\[[^\]]*\]\([^)]*\)/g, ' ')            // images
    .replace(/\[([^\]]+)\]\((?:https?:\/\/|\/)[^)]*\)/g, '$1')  // [text](url) → text
    .replace(/https?:\/\/\S+/g, ' ')
    .replace(/`+/g, '')
    .replace(/\*\*|__/g, '')
    .replace(/(^|\n)\s{0,3}(?:[-*•]|\d+[.)])\s+/g, '$1')  // list bullets
    .replace(/(^|\n)\s{0,3}#{1,6}\s+/g, '$1')         // headings
    .replace(/(^|\s)[*_](\S[^*_]*\S|\S)[*_](?=[\s.,!?;:]|$)/g, '$1$2')
    .replace(/[ \t]+/g, ' ')
    .replace(/\s*\n+\s*/g, ' ')
    .trim();
}

const SENTENCE_END = /[.!?…]+(?:["»)]+)?(?=\s|$)/g;
const MIN_SENTENCE_CHARS = 2;

/**
 * The complete sentences at the head of *buffer* and what is left. An abbreviation-like dot inside
 * a move («1.e4», «Кf3.») is not a boundary: a boundary needs whitespace or the end after it.
 */
export function takeSentences(buffer: string, final = false): { sentences: string[]; rest: string } {
  const sentences: string[] = [];
  let rest = buffer;
  for (;;) {
    SENTENCE_END.lastIndex = 0;
    const m = SENTENCE_END.exec(rest);
    if (!m) break;
    const cut = m.index + m[0].length;
    const head = rest.slice(0, cut).trim();
    rest = rest.slice(cut);
    if (head.length >= MIN_SENTENCE_CHARS) sentences.push(head);
  }
  if (final && rest.trim().length >= MIN_SENTENCE_CHARS) {
    sentences.push(rest.trim());
    rest = '';
  }
  return { sentences, rest };
}

/**
 * Whether the transcript heard so far is the student's whole utterance: speech energy stopped
 * SILENCE_MS ago, and the text has not changed for STT_STABLE_MS (with a terminal mark) or
 * STT_STABLE_SLOW_MS (without one). All times in ms on one clock.
 */
export function utteranceReady(
  transcript: string,
  now: number,
  lastChangeAt: number,
  lastSpeechAt: number | null,
): boolean {
  const text = transcript.trim();
  if (!text) return false;
  if (lastSpeechAt !== null && now - lastSpeechAt < SILENCE_MS) return false;
  const stable = now - lastChangeAt;
  if (/[.!?…]["»)]*$/.test(text)) return stable >= STT_STABLE_MS;
  return stable >= STT_STABLE_SLOW_MS;
}

/**
 * The words of the current utterance when the transcription model keeps a running transcript: what
 * came after *baseline* (the text already sent), else the whole text.
 */
export function newWords(transcript: string, baseline: string): string {
  const t = transcript.trim();
  const b = baseline.trim();
  if (b && t.startsWith(b)) return t.slice(b.length).trim();
  return t;
}

export type PipelineLocale = 'ru' | 'kk' | 'en';

/** The language of the student's words, for the filler and the TTS voice: Kazakh letters, Latin, else Russian. */
export function localeOf(text: string, fallback: PipelineLocale = 'ru'): PipelineLocale {
  const t = text || '';
  if (/[әғқңөұүһі]/i.test(t)) return 'kk';
  const latin = (t.match(/[a-z]/gi) || []).length;
  const cyr = (t.match(/[а-яё]/gi) || []).length;
  if (latin >= 3 && latin >= cyr * 2) return 'en';  // a word, not a bare move like «e4»
  if (cyr > 0) return 'ru';
  return fallback;
}

/** A canned spoken filler («Сейчас посмотрю») that plays at once while the text coach thinks. */
export const FILLERS: Record<PipelineLocale, string[]> = {
  ru: ['/voice/fillers/ru-1.pcm', '/voice/fillers/ru-2.pcm', '/voice/fillers/ru-3.pcm'],
  kk: ['/voice/fillers/kk-1.pcm', '/voice/fillers/kk-2.pcm'],
  en: ['/voice/fillers/en-1.pcm', '/voice/fillers/en-2.pcm'],
};

export function fillerFor(locale: PipelineLocale, pick: number = Math.random()): string {
  const list = FILLERS[locale] ?? FILLERS.ru;
  return list[Math.min(list.length - 1, Math.floor(pick * list.length))];
}
