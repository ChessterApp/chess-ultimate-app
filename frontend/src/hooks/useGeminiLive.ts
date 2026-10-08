import { useState, useRef, useCallback, useEffect } from 'react';
import { GoogleGenAI, Modality } from '@google/genai';
import type {
  LiveServerMessage,
  LiveServerToolCall,
  LiveServerToolCallCancellation,
  Session,
} from '@google/genai';

/**
 * useGeminiLive — browser-side Gemini Live voice client for the AI Chess Coach (Phase 2).
 *
 * Audio engine only: mints an ephemeral token via POST /api/coach/live-token, opens a Live
 * session through the SDK (ephemeral token passed as apiKey), streams 16 kHz PCM mic audio up
 * via an AudioWorklet, and plays back 24 kHz model audio gaplessly with barge-in support.
 * No UI — callers wire the returned state/handlers into their own components (Phase 3).
 */

export type LiveStatus = 'idle' | 'connecting' | 'listening' | 'speaking' | 'error';

// A student asking about a concept ("что такое связка", "покажи пример вилки",
// "what is a skewer"): the site fetches the knowledge-base example itself, puts
// it on the board and tells the model, like the [Engine] line. On production
// (2026-09-29) the 3.1 Live coach said "let me find an example" without calling
// get_topic and described a pin that was not on the board.
// A question about the position on the board («объясни, почему здесь связка», "what's the best move here")
// keeps it: the knowledge base's example must not replace the student's position, as Hermes' board lock
// keeps it for the text coach (2026-10-06; the voice lookup ran past it until 2026-10-08). Mirrors
// _ABOUT_POSITION / _WANTS_NEW_BOARD in hermes/src/server.py.
export const ABOUT_POSITION_RE =
  /(?<![а-яёa-z])(ход\S*|реши\S*|решени\S*|задач\S*|лучш\S*|играть|сыграть|сыграю|оцени\S*|позици\S*|здесь|тут|в\s+этой\s+позиции|на\s+доске|move|moves|solve|solution|puzzle|best|play|position|here|жүріс\S*|есеп\S*|осы\s+жерде)(?![а-яёa-z])/i;
export const WANTS_NEW_BOARD_RE =
  /(?<![а-яёa-z])(покажи|пример\S*|что\s+такое|объясни\s+тем\S*|загрузи|поставь|расставь|дай\s+(мне\s+)?(ещё\s+|новую\s+)?задач\S*|другую\s+задач\S*|следующ\S+\s+задач\S*|show\s+me|example|load|set\s+up|give\s+me\s+a(nother)?\s+puzzle|what\s+is\s+an?\b)(?![а-яёa-z])/i;
const START_BOARD = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR';

/** The utterance asks about the student's own position (not the start), so no example replaces it. */
export function keepsBoard(text: string, fen: string | undefined): boolean {
  if (!fen || fen.split(' ')[0] === START_BOARD) return false;
  return ABOUT_POSITION_RE.test(text) && !WANTS_NEW_BOARD_RE.test(text);
}

export const CONCEPT_QUESTION_RE =
  /(что\s+так(ое|ая|ой|ие)|объясни|расскажи\s+(мне\s+)?(про|о|об)\b|покажи\s+(мне\s+)?(пример|как)|пример\S*\s+\S+|что\s+значит|как\s+(играть|использовать|работает)|деген\s+не|түсіндір|мысал|what\s+is|what's\s+an?\b|explain|show\s+me\s+(an?\s+)?example|example\s+of)/i;
// Words that may name an opening («жареная печень», «детский мат», «против
// сицилианки», «в лондонскую»): the site asks Hermes' opening book (the same
// one the text coach gets before every answer) and, when it knows the name,
// puts the line on the board and tells the model — the voice coach on 3.1
// otherwise explains an opening it does not know from memory. The book
// answers «not found» cheaply, so the test is deliberately loose.
export const OPENING_HINT_RE =
  /(дебют|гамбит|защит|печен|(?:^|[^а-яё])мат(?:а|у|ом|е)?(?![а-яё])|систем|парти[яию]|атак|вариант|контратак|ловушк|сицилиан|испанск|итальянск|французск|каро|скандинав|славянск|индийск|нимцович|грюнфельд|английск|рети|пирц|алехин|петров|шотланд|венск|бенони|голландск|каталон|лондон|дракон|найдорф|берлин|траксл|полерио|эванс|легал|блэкберн|opening|gambit|defen[cs]e|attack|mate(?![a-z])|system|sicilian|spanish|ruy|italian|french|caro|scandinavian|slav|indian|london|dragon|najdorf|berlin|traxler|fried|liver|scholar|fool)/i;
// Wait this long after the last transcribed fragment: the student has finished
// the question, and the coach (≈1.5 s after speech ends) has not answered yet.
export const CONCEPT_LOOKUP_DELAY_MS = 400;
// A failed voice start is tried once more after this pause.
export const START_RETRY_DELAY_MS = 700;
// A move in the student's words («а если Rg1?», «поставлю ладью на g1», «взять
// ферзя конём», "what if I put the rook on g1"): the site plays it on the board
// and asks Stockfish about the position after it, and the model gets the
// "[Idea]" line before it answers — the voice twin of the text coach's block.
// On production (01.10) the voice coach, like the text one, said the rook on g1
// attacks the queen on h4 from its head. Cheap gate only: Hermes does the real parsing.
export const IDEA_MOVE_RE =
  /(?:^|[^A-Za-zА-Яа-яЁё])[KQRBNC][a-hабвсдефгх]?[1-8]?[x:×-]?[a-hабвсдефгх][1-8](?![0-9])|(?:^|[^А-Яа-яЁёA-Za-z])(?:Кр|[КСЛФ])[x:×х-]?[a-hабвсдефгх][1-8](?![0-9])|(?:^|[^0-9A-Za-zА-Яа-яЁё])[a-hабвсдефгх][1-8]\s?[-–—:x×]\s?[a-hабвсдефгх][1-8](?![0-9])|(?:^|[^0-9A-Za-z])[a-h][1-8][a-h][1-8](?![0-9])|(?:ладь|кон[яеёь]|слон|ферз|корол|пешк|rook|knight|bishop|queen|king|pawn)[а-яёa-z]*\s+(?:с\s+[a-hабвсдефгх][1-8]\s+|from\s+[a-h][1-8]\s+)?(?:(?:на|в|to|on|onto)\s+)?[a-hабвсдефгх][1-8](?![0-9])|(?:ладь|кон|слон|ферз|корол|пешк)[а-яё]*\s+(?:бь[её]т|берёт|берет|взять|бить|побить|съесть|забрать|забирает)\s+(?:на\s+)?[a-hабвсдефгх][1-8]|(?:взять|бить|побить|съесть|съем|забрать|срубить|возьму|бью|take|capture|grab)\s+(?:на\s+|on\s+)?(?:(?:пешку|коня|слона|ладью|ферзя)\s+(?:на\s+)?)?(?:[a-hабвсдефгх][1-8]|ферзя|коня|слона|ладью|короля|пешку|the\s+(?:queen|rook|knight|bishop|king|pawn))|(?:ладь|кон|слон|ферз|корол|пешк)[а-яё]*\s+(?:взять|бить|побить|съесть|забрать)|роки?[иеі]р|рок[еі]ровк|castl|(?:^|[^0-9A-Za-z-])[0O]-[0O](?![0-9])|(?:если|пойд[её]т|пойду|двин[а-яё]*|сыгра[а-яё]*|пешк[а-яё]*|what\s+about|how\s+about|\bif|\bplay|\bpush)[\s,:—-]+(?:[а-яёa-z]+\s+){0,2}[a-hабвсдефгх][1-8](?![0-9])/i;  // JS \w is Latin only; Cyrillic and transliterated files (е3, ф6, б5) count as squares (2026-10-08)
// Short: the [Idea] line came 0.3–0.8 s after the coach had started answering (voice bench, 2026-10-06).
export const IDEA_LOOKUP_DELAY_MS = 150;

// The coach's first words on a move question wait for the [Idea] verdict, at most this long (2026-10-08):
// the early cut of 07.10 still let the student hear 1–4 s of «хороший ход» before «это пат». 0 — off.
export const VOICE_IDEA_HOLD_MS = Number(process.env.NEXT_PUBLIC_VOICE_IDEA_HOLD_MS ?? 1000) || 0;
// A bad verdict already in, the coach not having said it: its first sentence is held until it shows
// whether it does (the [Idea] line often comes before the first word and is answered past anyway —
// voice bench 2026-10-08: 5 of 8 answers still let 0.3–1.2 s of it be heard).
export const VOICE_VERDICT_HOLD_MS = VOICE_IDEA_HOLD_MS > 0 ? Math.max(VOICE_IDEA_HOLD_MS, 1500) : 0;

/**
 * Holds the coach's audio while the verdict on the student's move is on its way: released as it was
 * when the verdict is harmless (or late — after *holdMs*), dropped when the coach is about to answer
 * past a blunder, a trapped piece or stalemate (it is then told the point and starts with it).
 */
export class IdeaAudioGate {
  private held: string[] = [];
  private pending = false;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private limit = 0;

  constructor(
    private readonly play: (b64: string) => void,
    private readonly holdMs: number,
  ) {}

  /** A move question was heard: the next audio waits for its verdict. */
  expect(): void {
    if (this.holdMs > 0) this.pending = true;
  }

  /** A bad verdict is known and not yet said: hold the coach's first sentence, at most *ms*. */
  watch(ms: number): void {
    if (ms <= 0) return;
    this.pending = true;
    this.limit = ms;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = setTimeout(() => this.release(), ms);
    }
  }

  audio(b64: string): void {
    if (!this.pending) {
      this.play(b64);
      return;
    }
    this.held.push(b64);
    if (!this.timer) this.timer = setTimeout(() => this.release(), this.limit || this.holdMs);
  }

  /** The verdict came (or never will): what was held plays now. */
  release(): void {
    this.stop();
    const held = this.held;
    this.held = [];
    held.forEach((b) => this.play(b));
  }

  /** The held words answer past the point of the move: never played. */
  drop(): void {
    this.stop();
    this.held = [];
  }

  get holding(): boolean {
    return this.held.length > 0;
  }

  get waiting(): boolean {
    return this.pending;
  }

  private stop(): void {
    if (this.timer) clearTimeout(this.timer);
    this.timer = null;
    this.pending = false;
    this.limit = 0;
  }
}

/** Words that show the coach told the student the point of a bad idea. */
export const VERDICT_SAID_RE: Record<string, RegExp> = {
  stalemate: /пат(?![а-яё])|ничь|stalemate|\bdraw|тепе-тең|пат\s/i,
  trapped: /пойма|ловушк|некуда\s+(?:уйти|отступ|деться)|запер|trapp|caught|no\s+(?:safe\s+)?square|ұста|тұзақ/i,
  blunder: /ошиб|зев|потер|теря|отда[её]|грубая|плох|blunder|mistake|los[et]|hang|қате|жоғалт/i,
};

/** The note that makes the coach say the point it left out (a blunder, a trapped piece, stalemate). */
export function verdictNote(verdict: { kind?: string; headline?: string } | null | undefined, said: string): string | null {
  if (!verdict?.kind || !verdict.headline) return null;
  const re = VERDICT_SAID_RE[verdict.kind];
  if (re && re.test(said)) return null;
  return (
    `[Idea] You have not told the student the main point of their move: ${verdict.headline}. ` +
    `Say it now in one or two short sentences, in the student's language, plainly; do not mention a note or a check.`
  ).replace(/\s+/g, ' ').trim();
}
// Tools the site calls itself from the student's words (see lookUpConcept).
export const SITE_FETCHED_TOOLS = new Set(['get_topic', 'lookup_opening', 'get_puzzle', 'review_game']);

// What the coach said is checked on the board sentence by sentence (the same
// check the text coach's answers pass before they are shown — a spoken
// sentence has been heard by the time its transcription arrives). A wrong one
// is read back to the model after its turn, and it corrects itself aloud.
export const SPEECH_SENTENCE_END_RE = /[.!?…](?:\s|$)/;
// Only sentences with chess content are worth a round trip.
export const SPEECH_CHECKABLE_RE = /[a-h][1-8]|\d|кон[ьяю]|слон|лад[ьё]|ферз|корол|пешк|knight|bishop|rook|queen|king|pawn/i;
export const SPEECH_CHECK_MAX_PER_TURN = 2;

/** The note that makes the coach correct a sentence that was wrong on the board. */
export function correctionNote(sentences: { text: string; issues: string[] }[]): string | null {
  if (!sentences.length) return null;
  const items = sentences
    .map((s) => `«${s.text.trim()}» — ${s.issues.join('; ')}`)
    .join(' ');
  return (
    `[Check] What you just said was checked on the board and is wrong: ${items}. ` +
    `Correct yourself now in one or two short sentences, in the student's language, ` +
    `naming only moves and attacks that are true on the board; do not mention a check or a mistake report.`
  ).replace(/\s+/g, ' ').trim();
}

// «Дай задачу на вилку», «реши задачу», «give me a puzzle»: the site fetches a
// verified puzzle itself (3.1 Live sometimes promised one and called nothing),
// puts it on the board and tells the model — solution included, privately, so
// it can judge the student's answer.
export const PUZZLE_REQUEST_RE =
  /(?:(?:дай|давай|хочу|можно|реши[мт]?|покажи|подбери|найди)\s+(?:мне\s+)?(?:ещ[её]\s+)?(?:одну\s+)?(?:задач|головолом|упражнен)|задач[уи]\s+на|есеп\s+бер|тапсырма|(?:give|show|find)\s+me\s+(?:a\s+|another\s+)?puzzle|(?:a\s+)?puzzle\s+(?:on|about|for)|solve\s+a\s+puzzle|let'?s\s+solve)/i;
// The theme named after «на» / «on»: «задачу на вилку» → «вилку».
export const PUZZLE_THEME_RE = /(?:задач[уи]|упражнени[ея]|puzzle)\s+(?:на|про|по|on|about|for)\s+([^,.!?]+)/i;

/** The note the model gets with a puzzle the site put on the board. */
export function puzzleNote(result: {
  theme?: string | null;
  rating?: number | null;
  puzzles?: { fen?: string; solution?: string[] | string; rating?: number; themes?: string[] }[];
  on_board?: string;
}): string | null {
  const first = result.puzzles?.[0];
  if (!first?.fen) return null;
  const side = first.fen.split(' ')[1] === 'b' ? 'Black' : 'White';
  const solution = Array.isArray(first.solution) ? first.solution.join(' ') : first.solution ?? '';
  return (
    `[Puzzle] A verified puzzle is now on the student's board: FEN ${first.fen}, ${side} to move` +
    `${result.theme ? `, theme ${result.theme}` : ''}${first.rating ? `, rating ${first.rating}` : ''}. ` +
    `Solution (private, never read it out unless the student gives up): ${solution}. ` +
    `Say whose move it is and what to look for, then let the student try; judge their answer against the solution. ` +
    `Do not call get_puzzle again for this request.`
  ).replace(/\s+/g, ' ').trim();
}

// «Разбери мою партию», «где я ошибся», «review my game»: when a game is on
// the board the site finds its critical moments itself (2–3 s, within the
// coach's «let me look») and hands them to the model — the text coach gets
// the same block before it answers.
export const REVIEW_REQUEST_RE =
  /(разбер[иё][а-яё]*|разбор|проанализир[а-яё]*\s+(?:мою\s+|эту\s+)?парти|где\s+я\s+ошиб|мои\s+ошибк|что\s+я\s+сделал\s+не\s+так|ойынымды\s+талда|review\s+(?:my\s+|the\s+|this\s+)?game|analy[sz]e\s+(?:my\s+|the\s+|this\s+)?game|where\s+did\s+i\s+go\s+wrong|my\s+mistakes)/i;
export const REVIEW_SIDE_RE = /(ч[её]рными|за\s+ч[её]рных|as\s+black|with\s+black)|(белыми|за\s+белых|as\s+white|with\s+white)/i;
export const REVIEW_MIN_PLIES = 10;

/** The note the model gets with the critical moments of the game on the board. */
export function reviewNote(result: { note?: string; moments?: unknown[] }): string | null {
  if (!result.note) return null;
  return `[Review] ${result.note}`.replace(/[ \t]+/g, ' ').trim();
}

/** The note the model gets with an opening the site looked up for the student. */
export function openingNote(result: {
  found?: boolean;
  name?: string;
  eco?: string;
  line?: string;
  loaded?: boolean;
  about_the_board?: boolean;
  note?: string;
}): string | null {
  if (!result.found || !result.note) return null;
  return `[Opening] ${result.note}`.replace(/\s+/g, ' ').trim();
}

/** The note the model gets with a knowledge-base example the site put on the board. */
export function topicNote(result: {
  title?: string;
  example?: {
    title?: string;
    fen?: string;
    note?: string;
    side_to_move?: string;
    // From the site's own lesson (get_topic, 2026-10-03): the student's programme comes first.
    source?: string;
    course?: string;
    url?: string;
    tasks?: number;
    solution?: string[];
    kind?: string;
    // The lesson's own text from the programme (steps 1–3), with its diagram.
    explanation?: string;
  };
}): string | null {
  const ex = result.example;
  if (!ex?.fen) return null;
  if (ex.source === 'site_lesson') {
    const where = `the site's lesson «${ex.title ?? ''}»${ex.course ? ` (course «${ex.course}»)` : ''}`;
    const tasks = ex.tasks && ex.tasks > 1 ? `, which has ${ex.tasks} tasks` : '';
    if (ex.kind === 'diagram') {
      const says = ex.explanation ? ` The lesson says: ${ex.explanation.slice(0, 700)}` : '';
      return (
        `[Topic] On the student's board is an explanatory diagram of ${where}${tasks} ` +
        `(FEN ${ex.fen}${ex.side_to_move ? `, ${ex.side_to_move} to move` : ''}).` +
        (ex.note ? ` It shows: ${ex.note}.` : '') +
        says +
        ` Explain «${result.title ?? ''}» in the lesson's own words with this very position, and at the end ` +
        `send the student to the whole lesson and its tasks, naming the lesson and course exactly as here` +
        (ex.url ? ` (address ${ex.url})` : '') +
        `. Describe no other example and do not call get_topic for it again.`
      ).replace(/\s+/g, ' ').trim();
    }
    const what = ex.kind === 'task' ? 'the first task' : 'the exercise';
    const solution = ex.solution && ex.solution.length > 0 ? ex.solution.join(' ') : '';
    return (
      `[Topic] On the student's board is ${what} of ${where}${tasks}, set as a puzzle ` +
      `(FEN ${ex.fen}${ex.side_to_move ? `, ${ex.side_to_move} to move` : ''}). ` +
      (solution ? `Its solution is ${solution} — do not reveal it unless the student asks or fails twice. ` : '') +
      `Explain «${result.title ?? ''}» with this very position, then invite the student to solve it, and at the end ` +
      `send them to the whole lesson, naming the lesson and course exactly as here` +
      (ex.url ? ` (address ${ex.url})` : '') +
      `. Describe no other example and do not call get_topic for it again.`
    ).replace(/\s+/g, ' ').trim();
  }
  return (
    `[Topic] The knowledge-base example for «${result.title ?? ''}» is now on the student's board: ` +
    `${ex.title ?? ''} (FEN ${ex.fen}${ex.side_to_move ? `, ${ex.side_to_move} to move` : ''}). ` +
    `${ex.note ?? ''} Explain exactly this position — describe no other example and do not ` +
    `call get_topic for it again.`
  ).replace(/\s+/g, ' ').trim();
}

export interface UseGeminiLiveOptions {
  getFen?: () => string;
  /** The moves on the board (PGN), when a game is loaded — for a review by voice. */
  getPgn?: () => string | null | undefined;
  /** Current coach session id, so the minted token carries the shared conversation memory. */
  getSessionId?: () => string | null | undefined;
  onTranscript?: (t: {
    role: 'user' | 'model';
    text: string;
    final: boolean;
    /** Turn correlation id for this utterance, so persisted rows join to events. */
    turnId?: string;
  }) => void;
  onError?: (msg: string) => void;
  onStatusChange?: (s: LiveStatus) => void;
  /** Fired after a voice tool call resolves, so the UI can apply board actions / game lists. */
  onToolResult?: (name: string, result: unknown) => void;
  /**
   * Fired when the monthly voice-minutes quota runs out — either the mint was
   * refused (429) or the local countdown reached zero and the session was ended.
   * The UI shows the "minutes used up" message instead of a connection error.
   */
  onQuotaExhausted?: () => void;
}

export interface UseGeminiLiveReturn {
  status: LiveStatus;
  isSupported: boolean;
  isActive: boolean;
  error: string | null;
  /** Acquire mic + audio contexts inside the tap handler, before any network work. */
  prepare: () => Promise<void>;
  connect: () => Promise<void>;
  /**
   * Ask for the session token ahead of the tap (the mic button calls it on
   * hover / focus / touch). It takes 1.4-3 s on chesster.io; connect() reuses it
   * while it is fresh and the board has not changed.
   */
  prefetch: () => void;
  disconnect: () => void;
  sendBoardUpdate: (fen: string) => void;
  /**
   * Voice minutes left this month, counted down locally from the mint response.
   * `null` when unknown (before connect), unlimited, or the quota lookup failed
   * open. Updated once per heartbeat tick while a session is live.
   */
  remainingSeconds: number | null;
}

// A token asked for ahead of the tap is used while younger than this. The route
// gives it 60 s to open a session (newSessionExpireTime); the rest is margin,
// and it keeps the conversation recap inside the token recent.
const PREFETCH_REUSE_MS = 40_000;

interface PrefetchedToken {
  fen: string | undefined;
  sessionId: string | null;
  at: number;
  response: Promise<Response>;
}

// Gemini Live audio formats (non-negotiable, per spec).
const OUTPUT_SAMPLE_RATE = 24000;
// RMS above which local mic activity counts as barge-in while the model is speaking.
const BARGE_IN_RMS = 0.05;
// ...and for how long: about a syllable of loud input, with gaps shorter than
// BARGE_IN_GAP_MS bridged. A single ~3 ms frame used to be enough, so a click,
// a cough or the coach's own voice leaking from the speakers cut him off
// mid-sentence (local check 2026-09-27). Gemini's own speech-aware
// `interrupted` signal still stops playback too.
const BARGE_IN_SUSTAIN_MS = 250;
const BARGE_IN_GAP_MS = 120;
// RMS above which a mic frame counts as speech — used to approximate VAD end
// (the user's last spoken frame) as the start of the time-to-first-audio window.
const SPEECH_RMS = 0.02;
// Cap a single tool call so the model never waits indefinitely on a slow tool;
// on timeout we reply with an error so it can verbally report it couldn't check.
const TOOL_CALL_TIMEOUT_MS = 10000;
// After this long on a healthy connection, restore the one-shot reconnect budget
// so a later, unrelated drop can still auto-recover.
const HEALTHY_RECONNECT_RESET_MS = 60000;
// How often to report accumulated voice seconds to the metering ledger and to
// re-evaluate the local minutes countdown while a session is live.
const VOICE_HEARTBEAT_INTERVAL_MS = 60000;

// Latency + lifecycle telemetry contract shared with Hermes POST /api/coach/metrics.
// 'end' is the metering beacon fired on disconnect (carries session_ms; the server
// meters a voice session row from it); 'session_end' is the event-log lifecycle
// beacon (carries end_reason). Phase 2 also adds reconnect / tool_timeout /
// barge_in for full voice-path instrumentation in coach_events.
type LiveMetricEvent =
  | 'connect'
  | 'reconnect'
  | 'turn'
  | 'tool'
  | 'tool_timeout'
  | 'barge_in'
  | 'error'
  | 'drop'
  | 'end'
  | 'session_end'
  | 'usage';
/** Why a voice session ended, carried on the 'session_end' beacon. */
type SessionEndReason = 'user_stop' | 'quota_exhausted' | 'error' | 'drop';
interface LiveMetricRecord {
  sessionId?: string;
  turn: number;
  event: LiveMetricEvent;
  /** Per-utterance correlation id (client-generated UUID), on every beacon. */
  turn_id?: string;
  ttfa_ms?: number;
  connect_ms?: number;
  token_ms?: number;
  tool_name?: string;
  tool_ms?: number;
  prompt_bytes?: number;
  /** Whole-session duration in ms, sent on the 'end'/'session_end' beacons. */
  session_ms?: number;
  /** Actual failure detail (DOMException name+message, or String(err)) for 'error' events. */
  error?: string;
  /** Tool-call outcome + failure code on 'tool'/'tool_timeout' beacons. */
  ok?: boolean;
  error_code?: string;
  /** End reason on the 'session_end' beacon. */
  end_reason?: SessionEndReason;
  /** Gemini usageMetadata for one model turn, on the 'usage' beacon. */
  prompt_tokens?: number;
  completion_tokens?: number;
  cached_tokens?: number;
  model?: string;
  ts: number;
}

// Per-utterance correlation id. Prefers crypto.randomUUID (present in all voice-
// capable browsers + the test env); falls back to a random token so telemetry
// never throws where it's unavailable.
function genTurnId(): string {
  try {
    if (typeof crypto !== 'undefined' && typeof crypto.randomUUID === 'function') {
      return crypto.randomUUID();
    }
  } catch {
    /* fall through */
  }
  return `t_${Math.random().toString(36).slice(2)}${Math.random().toString(36).slice(2)}`;
}

// Human/telemetry-readable failure text. Preserves the DOMException name (e.g.
// NotAllowedError) so a blocked mic is distinguishable from a network failure,
// both in the visible status pill and in the error metric.
function describeError(err: unknown, fallback: string): string {
  if (err instanceof DOMException) {
    return err.message ? `${err.name}: ${err.message}` : err.name;
  }
  if (err instanceof Error) {
    return err.message || fallback;
  }
  const s = String(err);
  return s && s !== '[object Object]' ? s : fallback;
}

function getAudioContextCtor(): typeof AudioContext | null {
  if (typeof window === 'undefined') return null;
  return (window.AudioContext ||
    (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext ||
    null) as typeof AudioContext | null;
}

function arrayBufferToBase64(buf: ArrayBuffer): string {
  const bytes = new Uint8Array(buf);
  let binary = '';
  const chunk = 0x8000;
  for (let i = 0; i < bytes.length; i += chunk) {
    binary += String.fromCharCode.apply(
      null,
      Array.from(bytes.subarray(i, i + chunk)),
    );
  }
  return btoa(binary);
}

// Minimal per-move context line the live model reads as the new source of truth.
// Kept terse (just the FEN) so injected board updates don't bloat the turn.
function boardUpdateText(fen: string): string {
  return `Current position (FEN): ${fen}`;
}

function base64ToInt16(b64: string): Int16Array {
  const binary = atob(b64);
  const len = binary.length;
  const bytes = new Uint8Array(len);
  for (let i = 0; i < len; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new Int16Array(bytes.buffer, 0, Math.floor(len / 2));
}

export default function useGeminiLive(
  options: UseGeminiLiveOptions = {},
): UseGeminiLiveReturn {
  const [status, setStatusState] = useState<LiveStatus>('idle');
  const [isSupported, setIsSupported] = useState(false);
  const [isActive, setIsActive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // Voice minutes left this month (see UseGeminiLiveReturn.remainingSeconds).
  const [remainingSeconds, setRemainingSeconds] = useState<number | null>(null);

  // Keep the latest options accessible from stable callbacks without re-binding them.
  const optionsRef = useRef<UseGeminiLiveOptions>(options);
  optionsRef.current = options;

  const statusRef = useRef<LiveStatus>('idle');
  const sessionRef = useRef<Session | null>(null);
  // Latest resumable session handle from the server, used to reconnect after an
  // unexpected drop. Null until the server sends a resumable update.
  const resumptionHandleRef = useRef<string | null>(null);
  // Set when the user deliberately stops — suppresses auto-reconnect.
  const userStoppedRef = useRef(false);
  // Guards to a single automatic reconnect per user-initiated session.
  const reconnectUsedRef = useRef(false);
  // Timer that restores the reconnect budget after a stretch of healthy uptime.
  const healthyTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // Bumped whenever a connection is torn down or replaced, so close/error
  // callbacks from a stale session are ignored (they must not trigger a drop).
  const connGenRef = useRef(0);
  const streamRef = useRef<MediaStream | null>(null);
  const captureCtxRef = useRef<AudioContext | null>(null);
  const playbackCtxRef = useRef<AudioContext | null>(null);
  const sourceNodeRef = useRef<MediaStreamAudioSourceNode | null>(null);
  const workletNodeRef = useRef<AudioWorkletNode | null>(null);
  // The capture context the pcm-capture worklet module is currently loaded on.
  // Re-adding the module to the same context throws ("already registered"), so
  // on a reconnect that reuses the context we skip addModule.
  const workletLoadedCtxRef = useRef<AudioContext | null>(null);
  const playSourcesRef = useRef<Set<AudioBufferSourceNode>>(new Set());
  const nextPlayTimeRef = useRef(0);
  // In-flight tool-call fetches, keyed by functionCall id, so a
  // toolCallCancellation can abort them.
  const toolAbortRef = useRef<Map<string, AbortController>>(new Map());
  // The board the session was last told about, and the in-flight [Engine]
  // note request for it (a newer position aborts the older request).
  const boardFenRef = useRef<string | null>(null);
  const engineNoteAbortRef = useRef<AbortController | null>(null);

  // ── Latency instrumentation ────────────────────────────────────────────────
  // Turn counter for per-turn TTFA records.
  const turnRef = useRef(0);
  // Client-generated correlation id for the current utterance/turn. Set lazily
  // when a turn begins (user speech / a tool call) and cleared at turn end, so a
  // fresh turn gets a fresh id. Stamped on every beacon + the transcript rows.
  const turnIdRef = useRef<string | null>(null);
  /** Model name the token was minted for; stamped on the 'usage' beacon. */
  const modelRef = useRef<string | null>(null);
  // performance.now() of the user's most recent spoken (above-threshold) mic
  // frame — approximates VAD end, the start of the time-to-first-audio window.
  const lastUserSpeechAtRef = useRef<number | null>(null);
  // Loud mic time accumulated while the coach speaks, and when it was last
  // loud — local barge-in needs BARGE_IN_SUSTAIN_MS of it.
  const bargeInLoudMsRef = useRef(0);
  const bargeInLastLoudAtRef = useRef<number | null>(null);
  // True while we're still waiting for the first model audio chunk of a turn,
  // so TTFA is measured once per turn (reset when playback drains / on barge-in).
  const firstAudioPendingRef = useRef(true);

  const setStatus = useCallback((s: LiveStatus) => {
    statusRef.current = s;
    setStatusState(s);
    optionsRef.current.onStatusChange?.(s);
  }, []);

  // Fire-and-forget a latency record to Hermes via the metrics proxy. This runs
  // OFF the audio hot path: never awaited, fully wrapped in try/catch, so a slow
  // or failing metrics endpoint can never delay or break voice.
  // Wall-clock start of the current live session (set on connect), used to
  // compute session_ms for the 'end' metering beacon.
  const sessionStartRef = useRef<number | null>(null);

  // ── Voice minutes metering ─────────────────────────────────────────────────
  // Remaining seconds at connect time (from the mint response); null = unknown /
  // unlimited, so no local enforcement. The countdown is derived from this minus
  // session elapsed time.
  const quotaInitialRef = useRef<number | null>(null);
  // Seconds already reported to the metering ledger for this session, so each
  // heartbeat only sends the newly-elapsed delta (survives reconnects).
  const bookedSecondsRef = useRef(0);
  // Periodic heartbeat/countdown timer while a session is live.
  const heartbeatTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  // Set below (after disconnect is defined) to gracefully end a session when the
  // monthly quota is exhausted mid-call.
  const endForQuotaRef = useRef<() => void>(() => {});

  // Return the current turn's correlation id, minting one if a turn is in flight
  // without a user-speech frame yet (e.g. a model-initiated tool call).
  const ensureTurnId = useCallback((): string => {
    if (!turnIdRef.current) turnIdRef.current = genTurnId();
    return turnIdRef.current;
  }, []);

  const reportMetric = useCallback(
    (partial: Partial<LiveMetricRecord> & { event: LiveMetricEvent }) => {
      const record: LiveMetricRecord = {
        sessionId: optionsRef.current.getSessionId?.() ?? undefined,
        turn: partial.turn ?? turnRef.current,
        event: partial.event,
        turn_id: partial.turn_id ?? turnIdRef.current ?? undefined,
        ttfa_ms: partial.ttfa_ms,
        connect_ms: partial.connect_ms,
        token_ms: partial.token_ms,
        tool_name: partial.tool_name,
        tool_ms: partial.tool_ms,
        prompt_bytes: partial.prompt_bytes,
        session_ms: partial.session_ms,
        error: partial.error,
        ok: partial.ok,
        error_code: partial.error_code,
        end_reason: partial.end_reason,
        prompt_tokens: partial.prompt_tokens,
        completion_tokens: partial.completion_tokens,
        cached_tokens: partial.cached_tokens,
        model: partial.model,
        ts: Date.now(),
      };
      try {
        console.debug('[live-metrics]', record);
        void fetch('/api/coach/metrics', {
          method: 'POST',
          headers: { 'Content-Type': 'application/json' },
          credentials: 'include',
          body: JSON.stringify(record),
          keepalive: true,
        }).catch(() => {
          /* telemetry only — swallow */
        });
      } catch {
        /* telemetry must never break the audio path */
      }
    },
    [],
  );

  // Fire-and-forget a metering heartbeat to the voice-usage proxy (which sets
  // the user server-side and forwards to Hermes). Off the audio hot path: never
  // awaited, fully wrapped, keepalive so a final flush survives page unload.
  const postHeartbeat = useCallback((secondsDelta: number) => {
    if (secondsDelta <= 0) return;
    const sessionId = optionsRef.current.getSessionId?.() ?? undefined;
    if (!sessionId) return;
    try {
      void fetch('/api/coach/voice-usage', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ session_id: sessionId, seconds_delta: secondsDelta }),
        keepalive: true,
      }).catch(() => {
        /* metering is best-effort — swallow */
      });
    } catch {
      /* metering must never break the audio path */
    }
  }, []);

  const stopHeartbeat = useCallback(() => {
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
  }, []);

  // Book the seconds elapsed since the last heartbeat and, when metered, update
  // the local countdown — ending the session gracefully once it hits zero.
  const heartbeatTick = useCallback(() => {
    if (sessionStartRef.current === null) return;
    const elapsedSec = Math.floor(
      (performance.now() - sessionStartRef.current) / 1000,
    );
    const delta = elapsedSec - bookedSecondsRef.current;
    if (delta > 0) {
      postHeartbeat(delta);
      bookedSecondsRef.current = elapsedSec;
    }
    if (quotaInitialRef.current !== null) {
      const remaining = Math.max(0, quotaInitialRef.current - elapsedSec);
      setRemainingSeconds(remaining);
      if (remaining <= 0) {
        endForQuotaRef.current();
      }
    }
  }, [postHeartbeat]);

  // End-of-session telemetry: flush the residual metered seconds, then emit the
  // metering 'end' beacon (unchanged) and the 'session_end' lifecycle beacon
  // (with the end reason). Guarded on sessionStartRef so it fires exactly once
  // per session — it nulls sessionStartRef, so a later call is a no-op.
  const emitSessionEnd = useCallback(
    (reason: SessionEndReason) => {
      if (sessionStartRef.current === null) return;
      const elapsedMs = performance.now() - sessionStartRef.current;
      const residual = Math.floor(elapsedMs / 1000) - bookedSecondsRef.current;
      if (residual > 0) {
        postHeartbeat(residual);
        bookedSecondsRef.current += residual;
      }
      const session_ms = Math.round(elapsedMs);
      reportMetric({ event: 'end', session_ms });
      reportMetric({ event: 'session_end', session_ms, end_reason: reason });
      sessionStartRef.current = null;
    },
    [postHeartbeat, reportMetric],
  );

  // Detect capability once mounted (SSR-safe).
  useEffect(() => {
    const supported =
      typeof window !== 'undefined' &&
      getAudioContextCtor() !== null &&
      typeof AudioWorkletNode !== 'undefined' &&
      !!navigator?.mediaDevices?.getUserMedia;
    setIsSupported(supported);
  }, []);

  // Stop and clear all scheduled playback buffers.
  const stopSources = useCallback(() => {
    playSourcesRef.current.forEach((src) => {
      try {
        src.onended = null;
        src.stop();
      } catch {
        /* already stopped */
      }
    });
    playSourcesRef.current.clear();
    nextPlayTimeRef.current = 0;
  }, []);

  // Barge-in: flush playback and hand the floor back to the user.
  const flushPlayback = useCallback(() => {
    stopSources();
    // The interrupted turn is over — arm TTFA measurement for the next one and
    // clear the turn id so the next utterance correlates under a fresh id.
    firstAudioPendingRef.current = true;
    turnIdRef.current = null;
    if (statusRef.current === 'speaking') {
      setStatus('listening');
    }
  }, [stopSources, setStatus]);

  // Tear down the live session and audio graph. With { keepMedia: true } the
  // mic stream and both AudioContexts are left alive (and the worklet module
  // stays loaded) so a reconnect can reuse them without a fresh user gesture —
  // re-acquiring them off-gesture would fail on mobile Safari.
  const cleanup = useCallback((opts?: { keepMedia?: boolean }) => {
    const keepMedia = opts?.keepMedia ?? false;
    // Invalidate the active connection so its late close/error callbacks no-op.
    connGenRef.current += 1;
    // Stop the metering/countdown timer; a reconnect restarts it in openConnection.
    if (heartbeatTimerRef.current) {
      clearInterval(heartbeatTimerRef.current);
      heartbeatTimerRef.current = null;
    }
    if (healthyTimerRef.current) {
      clearTimeout(healthyTimerRef.current);
      healthyTimerRef.current = null;
    }
    toolAbortRef.current.forEach((controller) => {
      try {
        controller.abort();
      } catch {
        /* noop */
      }
    });
    toolAbortRef.current.clear();
    engineNoteAbortRef.current?.abort();
    engineNoteAbortRef.current = null;
    boardFenRef.current = null;
    const node = workletNodeRef.current;
    if (node) {
      try {
        node.port.onmessage = null;
      } catch {
        /* noop */
      }
      try {
        node.disconnect();
      } catch {
        /* noop */
      }
      workletNodeRef.current = null;
    }
    if (sourceNodeRef.current) {
      try {
        sourceNodeRef.current.disconnect();
      } catch {
        /* noop */
      }
      sourceNodeRef.current = null;
    }
    if (!keepMedia && streamRef.current) {
      streamRef.current.getTracks().forEach((t) => {
        try {
          t.stop();
        } catch {
          /* noop */
        }
      });
      streamRef.current = null;
    }
    if (sessionRef.current) {
      try {
        sessionRef.current.close();
      } catch {
        /* noop */
      }
      sessionRef.current = null;
    }
    stopSources();
    if (!keepMedia) {
      if (captureCtxRef.current) {
        try {
          captureCtxRef.current.close();
        } catch {
          /* noop */
        }
        captureCtxRef.current = null;
      }
      if (playbackCtxRef.current) {
        try {
          playbackCtxRef.current.close();
        } catch {
          /* noop */
        }
        playbackCtxRef.current = null;
      }
      workletLoadedCtxRef.current = null;
    }
  }, [stopSources]);

  // Decode a base64 24 kHz PCM chunk and schedule it gaplessly.
  const enqueuePlayback = useCallback(
    (b64: string) => {
      const AudioCtor = getAudioContextCtor();
      if (!AudioCtor) return;
      if (!playbackCtxRef.current) {
        playbackCtxRef.current = new AudioCtor({ sampleRate: OUTPUT_SAMPLE_RATE });
      }
      const ctx = playbackCtxRef.current;

      const int16 = base64ToInt16(b64);
      if (int16.length === 0) return;

      // First audio chunk of a turn: record time-to-first-audio (VAD end →
      // first model audio). Measured once per turn, before any decode work.
      if (firstAudioPendingRef.current) {
        firstAudioPendingRef.current = false;
        const startedAt = lastUserSpeechAtRef.current;
        if (startedAt !== null) {
          turnRef.current += 1;
          reportMetric({
            event: 'turn',
            turn: turnRef.current,
            turn_id: ensureTurnId(),
            ttfa_ms: Math.round(performance.now() - startedAt),
          });
        }
      }

      const float = new Float32Array(int16.length);
      for (let i = 0; i < int16.length; i++) {
        float[i] = int16[i] / 0x8000;
      }

      const buffer = ctx.createBuffer(1, float.length, OUTPUT_SAMPLE_RATE);
      buffer.getChannelData(0).set(float);

      const src = ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(ctx.destination);

      const startAt = Math.max(ctx.currentTime, nextPlayTimeRef.current);
      src.start(startAt);
      nextPlayTimeRef.current = startAt + buffer.duration;

      playSourcesRef.current.add(src);
      setStatus('speaking');

      src.onended = () => {
        playSourcesRef.current.delete(src);
        if (playSourcesRef.current.size === 0 && statusRef.current === 'speaking') {
          // Model finished this turn — arm TTFA measurement for the next one and
          // clear the turn id so the next utterance gets a fresh one.
          firstAudioPendingRef.current = true;
          turnIdRef.current = null;
          setStatus('listening');
        }
      };
    },
    [setStatus, reportMetric, ensureTurnId],
  );
  // The coach's audio passes the gate: on a move question it waits for the verdict (IdeaAudioGate).
  const enqueuePlaybackRef = useRef(enqueuePlayback);
  enqueuePlaybackRef.current = enqueuePlayback;
  const ideaGateRef = useRef<IdeaAudioGate | null>(null);
  const ideaGate = useCallback((): IdeaAudioGate => {
    if (!ideaGateRef.current) {
      ideaGateRef.current = new IdeaAudioGate((b64) => enqueuePlaybackRef.current(b64), VOICE_IDEA_HOLD_MS);
    }
    return ideaGateRef.current;
  }, []);

  // Cancel in-flight tool fetches the model no longer wants a response for.
  const handleToolCancellation = useCallback(
    (cancellation: LiveServerToolCallCancellation) => {
      for (const id of cancellation.ids ?? []) {
        const controller = toolAbortRef.current.get(id);
        if (controller) {
          try {
            controller.abort();
          } catch {
            /* noop */
          }
          toolAbortRef.current.delete(id);
        }
      }
    },
    [],
  );

  // Run each functionCall through the /api/coach/tool proxy and reply with a
  // functionResponse for every call — even on failure — so the session never
  // stalls waiting on a tool.
  const handleToolCall = useCallback(async (toolCall: LiveServerToolCall) => {
    const calls = toolCall.functionCalls ?? [];
    const session = sessionRef.current;
    if (calls.length === 0 || !session) return;

    const sessionId = optionsRef.current.getSessionId?.() ?? undefined;

    const responses = await Promise.all(
      calls.map(async (fc) => {
        const controller = new AbortController();
        if (fc.id) toolAbortRef.current.set(fc.id, controller);
        // Correlate this tool call with the current turn's events.
        const toolTurnId = ensureTurnId();
        const toolStart = performance.now();
        let aborted = false;
        // Bound the tool at 10s. A timeout aborts the same controller, so we flag
        // it to tell a slow-tool timeout apart from a model-initiated cancel.
        let timedOut = false;
        // Tool-call outcome, recorded on the 'tool' beacon (success/failure was
        // previously never captured). error_code distinguishes proxy vs network.
        let toolOk = true;
        let toolErrorCode: string | undefined;
        const timeout = setTimeout(() => {
          timedOut = true;
          try {
            controller.abort();
          } catch {
            /* noop */
          }
        }, TOOL_CALL_TIMEOUT_MS);
        try {
          // The site already made this call for the student's words: the model
          // gets the same result — the board keeps what the student was told about.
          const siteResult = fc.name && SITE_FETCHED_TOOLS.has(fc.name) ? siteResultsRef.current.get(fc.name) : undefined;
          if (siteResult) {
            clearTimeout(timeout);
            return {
              id: fc.id,
              name: fc.name,
              response: { result: (siteResult as { result?: unknown }).result ?? siteResult },
            };
          }
          const res = await fetch('/api/coach/tool', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            credentials: 'include',
            body: JSON.stringify({
              name: fc.name,
              args: fc.args ?? {},
              session_id: sessionId,
            }),
            signal: controller.signal,
          });
          const data = await res.json().catch(() => ({}));
          if (!res.ok) {
            // Proxy/rate-limit rejection — the tool did NOT execute server-side,
            // so this outcome is captured only via the beacon.
            toolOk = false;
            toolErrorCode = `http_${res.status}`;
            return {
              id: fc.id,
              name: fc.name,
              response: {
                error:
                  (data && (data as { error?: string }).error) ||
                  `Tool proxy error ${res.status}`,
              },
            };
          }
          try {
            optionsRef.current.onToolResult?.(fc.name ?? '', data);
          } catch {
            /* UI callback errors must not break the session */
          }
          return {
            id: fc.id,
            name: fc.name,
            response: { result: (data as { result?: unknown }).result ?? data },
          };
        } catch (err) {
          if (err instanceof DOMException && err.name === 'AbortError') {
            // Timed out — still answer, with an error, so the model can say out
            // loud it couldn't check instead of stalling the turn silently.
            if (timedOut) {
              toolOk = false;
              toolErrorCode = 'timeout';
              return {
                id: fc.id,
                name: fc.name,
                response: {
                  error: `Tool "${fc.name ?? 'unknown'}" timed out after ${
                    TOOL_CALL_TIMEOUT_MS / 1000
                  }s`,
                },
              };
            }
            // Cancelled by the model — drop it, no response expected.
            aborted = true;
            return null;
          }
          toolOk = false;
          toolErrorCode = 'network';
          const message = err instanceof Error ? err.message : 'tool call failed';
          return { id: fc.id, name: fc.name, response: { error: message } };
        } finally {
          clearTimeout(timeout);
          if (fc.id) toolAbortRef.current.delete(fc.id);
          // Per-call tool telemetry: functionCall received → response ready.
          // Skip cancelled calls (no response is sent for them). A timeout gets a
          // dedicated 'tool_timeout' beacon; every other outcome (success or a
          // client-observed failure) rides the 'tool' beacon with ok/error_code.
          if (!aborted) {
            const tool_ms = Math.round(performance.now() - toolStart);
            if (timedOut) {
              reportMetric({
                event: 'tool_timeout',
                tool_name: fc.name ?? undefined,
                turn_id: toolTurnId,
                tool_ms,
                ok: false,
                error_code: 'timeout',
              });
            } else {
              reportMetric({
                event: 'tool',
                tool_name: fc.name ?? undefined,
                turn_id: toolTurnId,
                tool_ms,
                ok: toolOk,
                error_code: toolErrorCode,
              });
            }
          }
        }
      }),
    );

    const functionResponses = responses.filter(
      (r): r is NonNullable<typeof r> => r !== null,
    );
    if (functionResponses.length === 0) return;
    try {
      session.sendToolResponse({ functionResponses });
    } catch {
      /* session may be closing */
    }
  }, [reportMetric, ensureTurnId]);

  // Gemini rarely marks a transcription `finished`, so an utterance also ends at
  // the turn's edges: the student's when the coach starts answering (speech or a
  // tool call), the coach's when its turn completes or is cut off. Without this
  // every utterance of a call merged into one bubble and no voice line reached
  // the session history — a reload lost the talk, the text coach never saw it.
  const openUtterancesRef = useRef({ user: false, model: false });
  // The student's current utterance (fragments joined) and whether its concept
  // example was already looked up — see CONCEPT_QUESTION_RE.
  const userUtteranceRef = useRef('');
  const conceptDoneRef = useRef(false);
  const conceptTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The student's idea (a move in their words) already sent for this utterance — see IDEA_MOVE_RE.
  const ideaSentRef = useRef('');
  const ideaTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  // The point of the student's idea the coach must say (from voice/idea), and what
  // the coach has said since the student spoke — checked when the turn completes.
  const ideaVerdictRef = useRef<{ kind?: string; headline?: string } | null>(null);
  const modelTurnTextRef = useRef('');

  // The coach's current sentence (output transcription fragments joined), the
  // wrong ones of this turn, and how many checks were sent this turn.
  const modelSentenceRef = useRef('');
  const wrongSentencesRef = useRef<{ text: string; issues: string[] }[]>([]);
  const speechChecksRef = useRef(0);
  const speechCheckPendingRef = useRef<Promise<void>[]>([]);

  const checkSpokenSentence = useCallback(async (sentence: string, session: NonNullable<typeof sessionRef.current>) => {
    if (!SPEECH_CHECKABLE_RE.test(sentence) || sentence.trim().split(/\s+/).length < 4) return;
    if (speechChecksRef.current >= SPEECH_CHECK_MAX_PER_TURN) return;
    speechChecksRef.current += 1;
    try {
      const res = await fetch('/api/coach/voice/check', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          text: sentence,
          fen: optionsRef.current.getFen?.(),
          question: userUtteranceRef.current || undefined,
        }),
      });
      if (!res.ok) return;
      const data = (await res.json().catch(() => null)) as { issues?: string[] } | null;
      if (sessionRef.current !== session) return;
      if (Array.isArray(data?.issues) && data.issues.length) {
        wrongSentencesRef.current.push({ text: sentence, issues: data.issues });
      }
    } catch {
      /* unavailable (an older Hermes answers 404) — the coach is simply not corrected */
    }
  }, []);

  // What the site fetched for the current utterance, by tool name: when the
  // model then calls the same tool itself (it often decides to at the same
  // moment), it gets this result instead of a second fetch — otherwise the
  // puzzle on the board and the puzzle in the model's note were two different
  // puzzles (production, 01.10).
  const siteResultsRef = useRef<Map<string, unknown>>(new Map());

  // One voice tool call the site makes on the student's behalf; the result's
  // board actions reach the board and the note reaches the model.
  const siteToolCall = useCallback(async (
    name: string,
    args: Record<string, unknown>,
    session: NonNullable<typeof sessionRef.current>,
    makeNote: (result: never) => string | null,
  ): Promise<boolean> => {
    try {
      const res = await fetch('/api/coach/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ name, args, session_id: optionsRef.current.getSessionId?.() ?? undefined }),
      });
      if (!res.ok) return false;
      const data = (await res.json().catch(() => null)) as { result?: unknown; board_actions?: unknown[]; error?: unknown } | null;
      if (!data?.result || data.error) return false;
      const note = makeNote(data.result as never);
      if (!note) return false;
      if (sessionRef.current !== session) return false;
      siteResultsRef.current.set(name, data);
      try {
        optionsRef.current.onToolResult?.(name, data);
      } catch {
        /* UI callback errors must not break the session */
      }
      session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: note }] }], turnComplete: false });
      return true;
    } catch {
      return false; /* unavailable (an older Hermes) — the coach can still call the tool itself */
    }
  }, []);

  const lookUpPuzzle = useCallback(async (text: string, session: NonNullable<typeof sessionRef.current>) => {
    const theme = PUZZLE_THEME_RE.exec(text)?.[1]?.trim();
    if (theme && (await siteToolCall('get_puzzle', { theme, count: 1 }, session, puzzleNote))) return true;
    return siteToolCall('get_puzzle', { count: 1 }, session, puzzleNote);
  }, [siteToolCall]);

  const lookUpReview = useCallback(async (text: string, session: NonNullable<typeof sessionRef.current>) => {
    const pgn = optionsRef.current.getPgn?.();
    if (!pgn || pgn.replace(/\d+\.(\.\.)?/g, ' ').trim().split(/\s+/).length < REVIEW_MIN_PLIES) return false;
    const m = REVIEW_SIDE_RE.exec(text);
    const side = m ? (m[1] ? 'black' : 'white') : undefined;
    return siteToolCall('review_game', { pgn, side }, session, reviewNote);
  }, [siteToolCall]);

  const lookUpOpening = useCallback(async (text: string, session: NonNullable<typeof sessionRef.current>) => {
    try {
      const res = await fetch('/api/coach/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: 'lookup_opening',
          args: { question: text, fen: optionsRef.current.getFen?.() },
          session_id: optionsRef.current.getSessionId?.() ?? undefined,
        }),
      });
      if (!res.ok) return false;
      const data = (await res.json().catch(() => null)) as
        | { result?: Parameters<typeof openingNote>[0]; board_actions?: unknown[] }
        | null;
      const note = data?.result ? openingNote(data.result) : null;
      if (!note) return false;
      if (sessionRef.current !== session) return false;
      try {
        optionsRef.current.onToolResult?.('lookup_opening', data);
      } catch {
        /* UI callback errors must not break the session */
      }
      session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: note }] }], turnComplete: false });
      return true;
    } catch {
      return false; /* unavailable — the coach can still call lookup_opening itself */
    }
  }, []);

  const lookUpConcept = useCallback(async (text: string) => {
    if (conceptDoneRef.current || text.trim().split(/\s+/).length < 2) return;
    const session = sessionRef.current;
    if (!session) return;
    // A puzzle or a review asked for: the site fetches it; the coach only talks.
    if (PUZZLE_REQUEST_RE.test(text)) {
      conceptDoneRef.current = true;
      void lookUpPuzzle(text, session);
      return;
    }
    if (REVIEW_REQUEST_RE.test(text)) {
      conceptDoneRef.current = true;
      if (await lookUpReview(text, session)) return;
    }
    // An opening named in the words wins over a concept («что такое жареная
    // печень» is the Fried Liver, not the knowledge base's «печень»).
    if (OPENING_HINT_RE.test(text)) {
      conceptDoneRef.current = true;
      if (await lookUpOpening(text, session)) return;
      if (!CONCEPT_QUESTION_RE.test(text)) return;
    } else if (!CONCEPT_QUESTION_RE.test(text)) {
      return;
    }
    // «Объясни, почему здесь связка»: about the position on the board — the coach explains it from the
    // [Engine] line; the knowledge base's example must not take its place.
    if (keepsBoard(text, optionsRef.current.getFen?.())) return;
    conceptDoneRef.current = true;
    try {
      const res = await fetch('/api/coach/tool', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          name: 'get_topic',
          args: { topic: text },
          session_id: optionsRef.current.getSessionId?.() ?? undefined,
        }),
      });
      if (!res.ok) return;
      const data = (await res.json().catch(() => null)) as
        | { result?: Parameters<typeof topicNote>[0]; board_actions?: unknown[] }
        | null;
      const note = data?.result ? topicNote(data.result) : null;
      // No match or an ambiguous one: leave the concept to the coach's own tools.
      if (!note || !Array.isArray(data?.board_actions) || data.board_actions.length === 0) return;
      if (sessionRef.current !== session) return;
      siteResultsRef.current.set('get_topic', data);
      try {
        optionsRef.current.onToolResult?.('get_topic', data);
      } catch {
        /* UI callback errors must not break the session */
      }
      session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: note }] }], turnComplete: false });
    } catch {
      /* unavailable — the coach can still call get_topic itself */
    }
  }, [lookUpOpening, lookUpPuzzle, lookUpReview]);
  // The student names a move: play it on the board at Hermes, let Stockfish look
  // at the position after it, and hand the model the "[Idea]" line — before it
  // answers from its head (text coach: src/hypothetical.py, same facts).
  const lookUpIdea = useCallback(async (text: string) => {
    const session = sessionRef.current;
    if (!session || !IDEA_MOVE_RE.test(text) || ideaSentRef.current === text) return;
    const fen = optionsRef.current.getFen?.();
    if (!fen) {
      ideaGate().release();
      return;
    }
    ideaSentRef.current = text;
    let dropped = false;
    try {
      const res = await fetch('/api/coach/voice/idea', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({ text, fen }),
      });
      if (!res.ok) return;
      const data = (await res.json().catch(() => null)) as
        | { note?: unknown; moves?: unknown[]; verdict?: { kind?: string; headline?: string } | null }
        | null;
      const note = data?.note;
      if (typeof note !== 'string' || !note) return;
      if (sessionRef.current !== session || optionsRef.current.getFen?.() !== fen) return;
      ideaVerdictRef.current = data?.verdict && typeof data.verdict === 'object' ? data.verdict : null;
      try {
        optionsRef.current.onToolResult?.('voice_idea', data);
      } catch {
        /* UI callback errors must not break the session */
      }
      session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: note }] }], turnComplete: false });
      // The coach is already answering without these facts (the line comes 0.3–0.8 s after
      // it starts): a blunder, a trapped piece or stalemate it has not said yet is said now —
      // it stops and says it, instead of finishing an answer built on a guess and adding the
      // point at the end (production voice, 2026-10-07: «b3 возможен…», then «b3 — ошибка»).
      const early = modelTurnTextRef.current.trim() ? verdictNote(ideaVerdictRef.current, modelTurnTextRef.current) : null;
      if (early) {
        ideaVerdictRef.current = null;
        // What the coach has said so far (held, not yet heard) answers past the point: it is not played.
        ideaGate().drop();
        dropped = true;
        session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: early }] }], turnComplete: true });
      }
    } catch {
      /* unavailable (an older Hermes answers 404) — the coach answers without the line */
    } finally {
      if (!dropped) {
        if (ideaVerdictRef.current && verdictNote(ideaVerdictRef.current, modelTurnTextRef.current)) {
          ideaGate().watch(VOICE_VERDICT_HOLD_MS);  // its first sentence shows whether it says the point
        } else {
          ideaGate().release();
        }
      }
    }
  }, [ideaGate]);

  const closeUtterance = useCallback((role: 'user' | 'model') => {
    if (!openUtterancesRef.current[role]) return;
    openUtterancesRef.current[role] = false;
    optionsRef.current.onTranscript?.({
      role,
      text: '',
      final: true,
      turnId: turnIdRef.current ?? undefined,
    });
  }, []);

  const handleMessage = useCallback(
    (msg: LiveServerMessage) => {
      // Keep the latest resumable handle so we can reconnect after a drop.
      const resume = msg.sessionResumptionUpdate;
      if (resume?.resumable && resume.newHandle) {
        resumptionHandleRef.current = resume.newHandle;
      }

      if (msg.toolCall) {
        closeUtterance('user');
        void handleToolCall(msg.toolCall);
      }
      if (msg.toolCallCancellation) {
        handleToolCancellation(msg.toolCallCancellation);
      }

      // Token usage for the model turn just produced. Relayed to Hermes so the
      // voice surface is metered in real tokens (it used to be recorded as $0).
      const usage = msg.usageMetadata;
      if (usage && ((usage.promptTokenCount ?? 0) > 0 || (usage.responseTokenCount ?? 0) > 0)) {
        reportMetric({
          event: 'usage',
          turn_id: turnIdRef.current ?? undefined,
          prompt_tokens: usage.promptTokenCount ?? 0,
          completion_tokens: usage.responseTokenCount ?? 0,
          cached_tokens: usage.cachedContentTokenCount ?? 0,
          model: modelRef.current ?? undefined,
        });
      }

      const sc = msg.serverContent;
      if (!sc) return;

      if (sc.inputTranscription?.text) {
        // A user utterance starts a turn; mint the id now so the transcript row
        // and the turn's events (tool_call, turn_end) share one turn_id.
        const final = !!sc.inputTranscription.finished;
        if (!openUtterancesRef.current.user) {
          userUtteranceRef.current = '';
          conceptDoneRef.current = false;
          ideaSentRef.current = '';
          ideaVerdictRef.current = null;
          modelTurnTextRef.current = '';
          siteResultsRef.current.clear();
        }
        userUtteranceRef.current += sc.inputTranscription.text;
        const utterance = userUtteranceRef.current;
        if (conceptTimerRef.current) clearTimeout(conceptTimerRef.current);
        conceptTimerRef.current = setTimeout(() => void lookUpConcept(utterance), CONCEPT_LOOKUP_DELAY_MS);
        if (IDEA_MOVE_RE.test(utterance)) {
          ideaGate().expect();
          if (ideaTimerRef.current) clearTimeout(ideaTimerRef.current);
          ideaTimerRef.current = setTimeout(() => void lookUpIdea(utterance), IDEA_LOOKUP_DELAY_MS);
        }
        openUtterancesRef.current.user = !final;
        optionsRef.current.onTranscript?.({
          role: 'user',
          text: sc.inputTranscription.text,
          final,
          turnId: ensureTurnId(),
        });
      }
      if (sc.outputTranscription?.text) {
        closeUtterance('user');
        const final = !!sc.outputTranscription.finished;
        openUtterancesRef.current.model = !final;
        optionsRef.current.onTranscript?.({
          role: 'model',
          text: sc.outputTranscription.text,
          final,
          turnId: turnIdRef.current ?? undefined,
        });
        // Each finished sentence of the coach goes to the board check.
        modelSentenceRef.current += sc.outputTranscription.text;
        modelTurnTextRef.current += sc.outputTranscription.text;
        if (ideaGate().waiting && ideaVerdictRef.current && !verdictNote(ideaVerdictRef.current, modelTurnTextRef.current)) {
          ideaGate().release();  // the coach is saying the point: what it held plays
        }
        const session = sessionRef.current;
        let m: RegExpExecArray | null;
        while (session && (m = SPEECH_SENTENCE_END_RE.exec(modelSentenceRef.current))) {
          const sentence = modelSentenceRef.current.slice(0, m.index + 1);
          modelSentenceRef.current = modelSentenceRef.current.slice(m.index + m[0].length);
          speechCheckPendingRef.current.push(checkSpokenSentence(sentence, session));
          // A sentence done and the point of the student's idea still unsaid, though the
          // [Idea] line is in: said now, not after a whole answer past it (voice bench
          // 2026-10-07: 5 of 9 answers ignored a line that came before them).
          const early = verdictNote(ideaVerdictRef.current, modelTurnTextRef.current);
          if (early) {
            ideaVerdictRef.current = null;
            ideaGate().drop();  // a sentence past the point, never heard
            session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: early }] }], turnComplete: true });
          } else if (ideaGate().waiting && ideaVerdictRef.current) {
            ideaGate().release();  // the first sentence said the point
          }
        }
      }

      if (sc.interrupted) {
        ideaGate().drop();
        flushPlayback();
        closeUtterance('model');
        modelSentenceRef.current = '';
        wrongSentencesRef.current = [];
        speechChecksRef.current = 0;
      }
      if (sc.turnComplete) {
        closeUtterance('user');
        closeUtterance('model');
        // The turn is over: whatever was wrong is read back, and the coach
        // corrects itself — a new short turn, after the answer, never cutting it.
        const session = sessionRef.current;
        const pending = speechCheckPendingRef.current;
        speechCheckPendingRef.current = [];
        modelSentenceRef.current = '';
        speechChecksRef.current = 0;
        void Promise.all(pending).then(() => {
          const wrong = wrongSentencesRef.current;
          wrongSentencesRef.current = [];
          // The point of a bad idea left unsaid (the [Idea] line often arrives after
          // the coach has started talking) is said now, with any correction.
          const followUp = verdictNote(ideaVerdictRef.current, modelTurnTextRef.current);
          if (followUp) ideaVerdictRef.current = null;
          const note = [correctionNote(wrong), followUp].filter(Boolean).join(' ') || null;
          if (!note || !session || sessionRef.current !== session) return;
          try {
            optionsRef.current.onToolResult?.('voice_check', { result: { corrected: wrong } });
          } catch {
            /* UI callback errors must not break the session */
          }
          session.sendClientContent({ turns: [{ role: 'user', parts: [{ text: note }] }], turnComplete: true });
        });
      }

      const parts = sc.modelTurn?.parts;
      if (parts) {
        for (const part of parts) {
          const inline = part.inlineData;
          if (inline?.data && inline.mimeType?.includes('audio/pcm')) {
            ideaGate().audio(inline.data);
          }
        }
      }
    },
    [flushPlayback, ideaGate, handleToolCall, handleToolCancellation, ensureTurnId, closeUtterance, lookUpConcept, lookUpIdea, checkSpokenSentence],
  );

  const fail = useCallback(
    (msg: string) => {
      cleanup();
      setIsActive(false);
      setError(msg);
      optionsRef.current.onError?.(msg);
      setStatus('error');
      // Carry the real failure detail into telemetry so the 'error' event is
      // diagnosable (previously it reported an empty error).
      reportMetric({ event: 'error', error: msg });
      // Close out the session lifecycle. A terminal drop calls emitSessionEnd
      // with 'drop' first (so this no-ops); other failures land as 'error'.
      emitSessionEnd('error');
    },
    [cleanup, setStatus, reportMetric, emitSessionEnd],
  );

  // Acquire the mic and BOTH AudioContexts. This is the gesture-critical step:
  // on mobile Safari the user-activation window closes after any network await,
  // so getUserMedia + AudioContext.resume() must run before token mint / WS
  // connect or they reject/stay suspended. Idempotent — on a reconnect it
  // reuses the still-alive stream and contexts and just re-resumes them.
  const acquireMedia = useCallback(async () => {
    const AudioCtor = getAudioContextCtor();
    if (!AudioCtor) throw new Error('AudioContext is not available');

    // Mic first, before any await that isn't the getUserMedia prompt itself.
    if (!streamRef.current) {
      streamRef.current = await navigator.mediaDevices.getUserMedia({
        audio: { channelCount: 1, echoCancellation: true, noiseSuppression: true },
      });
    }

    // Capture context (native rate for mic input).
    if (!captureCtxRef.current) {
      captureCtxRef.current = new AudioCtor();
    }
    // Playback context (fixed 24 kHz model output). Created inside the gesture
    // too, so it isn't stuck suspended when the first model audio arrives.
    if (!playbackCtxRef.current) {
      playbackCtxRef.current = new AudioCtor({ sampleRate: OUTPUT_SAMPLE_RATE });
    }

    for (const ctx of [captureCtxRef.current, playbackCtxRef.current]) {
      if (ctx.state !== 'running' && typeof ctx.resume === 'function') {
        try {
          await ctx.resume();
        } catch {
          /* already running or closing — safe to ignore */
        }
      }
    }
  }, []);

  // Wire the held mic stream into the capture worklet and start streaming PCM.
  // Assumes acquireMedia() already ran, so the stream and capture context are
  // live — this only builds the audio graph (no getUserMedia, no ctx creation).
  const wireCapture = useCallback(
    async (session: Session) => {
      const ctx = captureCtxRef.current;
      const stream = streamRef.current;
      if (!ctx || !stream) throw new Error('Audio capture was not initialized');

      // Load the worklet module once per context; on a reused (reconnect)
      // context it is already registered, so re-adding it would throw.
      if (workletLoadedCtxRef.current !== ctx) {
        await ctx.audioWorklet.addModule('/worklets/pcm-capture-processor.js');
        workletLoadedCtxRef.current = ctx;
      }

      const source = ctx.createMediaStreamSource(stream);
      const node = new AudioWorkletNode(ctx, 'pcm-capture-processor');
      sourceNodeRef.current = source;
      workletNodeRef.current = node;

      node.port.onmessage = (ev: MessageEvent) => {
        const data = ev.data as { pcm: ArrayBuffer; rms: number };
        if (!data?.pcm) return;

        // Track the user's last spoken frame as the TTFA window start (VAD end
        // approximation). The mic streams continuously, so gate on speech energy.
        if (data.rms > SPEECH_RMS) {
          lastUserSpeechAtRef.current = performance.now();
          // A new utterance begins the moment the model isn't speaking — mint the
          // turn id here so tool calls fired before any audio share it.
          if (firstAudioPendingRef.current) ensureTurnId();
        }

        // Local barge-in: the user keeps talking over the coach. Record it (with
        // the turn it interrupted) BEFORE flushPlayback clears the turn id.
        const now = performance.now();
        const quietTooLong =
          bargeInLastLoudAtRef.current !== null && now - bargeInLastLoudAtRef.current > BARGE_IN_GAP_MS;
        if (quietTooLong) bargeInLoudMsRef.current = 0;
        if (data.rms > BARGE_IN_RMS && statusRef.current === 'speaking') {
          bargeInLoudMsRef.current += (data.pcm.byteLength / 2 / 16000) * 1000;
          bargeInLastLoudAtRef.current = now;
          if (bargeInLoudMsRef.current >= BARGE_IN_SUSTAIN_MS) {
            bargeInLoudMsRef.current = 0;
            reportMetric({
              event: 'barge_in',
              turn_id: turnIdRef.current ?? undefined,
              turn: turnRef.current,
            });
            flushPlayback();
          }
        }

        try {
          session.sendRealtimeInput({
            audio: {
              data: arrayBufferToBase64(data.pcm),
              mimeType: 'audio/pcm;rate=16000',
            },
          });
        } catch {
          /* session may be closing */
        }
      };

      source.connect(node);
      node.connect(ctx.destination);
    },
    [flushPlayback, reportMetric, ensureTurnId],
  );

  // Tell the live session about a board position: the FEN at once, then
  // Stockfish's top moves as an "[Engine] …" line when Hermes has them (1–2 s
  // for a new position, instant from its cache). With the line in context the
  // coach answers "what's the best move here?" without a tool round trip. Any
  // failure just means no line — the coach falls back to analyze_position.
  const sendPosition = useCallback((session: Session, fen: string) => {
    boardFenRef.current = fen;
    try {
      session.sendClientContent({
        turns: [{ role: 'user', parts: [{ text: boardUpdateText(fen) }] }],
        turnComplete: false,
      });
    } catch {
      /* session may be closing */
    }
    engineNoteAbortRef.current?.abort();
    const controller = new AbortController();
    engineNoteAbortRef.current = controller;
    void fetch('/api/coach/voice/engine-note', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      credentials: 'include',
      body: JSON.stringify({ fen }),
      signal: controller.signal,
    })
      .then((res) => (res.ok ? res.json() : null))
      .then((data: { note?: unknown } | null) => {
        const note = data?.note;
        // Drop a note for a position the board has already left.
        if (typeof note !== 'string' || !note || boardFenRef.current !== fen) return;
        if (sessionRef.current !== session) return;
        // 3.1 Live called analyze_position for a position it had this line for
        // (+1.5 s before the first word on «what should I play»); the line says
        // so itself now, where the model reads it.
        const directive = ' This IS the analysis of the current position: answer from it — do not call analyze_position for this FEN.';
        session.sendClientContent({
          turns: [{ role: 'user', parts: [{ text: note + directive }] }],
          turnComplete: false,
        });
      })
      .catch(() => {
        /* aborted or unavailable — no engine line this time */
      });
  }, []);

  // Lets the connection callbacks reach the drop handler without a dependency
  // cycle (the drop handler in turn re-opens the connection).
  const handleDropRef = useRef<(errMsg?: string) => void>(() => {});

  // A session token asked for ahead of the tap (see prefetch). One use: the
  // token itself is single-use, and it carries the FEN it was minted for.
  const prefetchedRef = useRef<PrefetchedToken | null>(null);

  const requestToken = useCallback(
    (fen: string | undefined, sessionId: string | null | undefined, resumeHandle?: string) =>
      fetch('/api/coach/live-token', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'include',
        body: JSON.stringify({
          fen,
          session_id: sessionId ?? undefined,
          resume: resumeHandle ?? undefined,
        }),
      }),
    [],
  );

  const prefetch = useCallback(() => {
    if (sessionRef.current) return;
    const fen = optionsRef.current.getFen?.();
    const current = prefetchedRef.current;
    if (current && current.fen === fen && Date.now() - current.at < PREFETCH_REUSE_MS) return;
    const sessionId = optionsRef.current.getSessionId?.();
    const response = requestToken(fen, sessionId);
    // A failed prefetch is simply not used: connect() asks again and reports.
    response.catch(() => {});
    prefetchedRef.current = { fen, sessionId: sessionId ?? null, at: Date.now(), response };
  }, [requestToken]);

  /** The prefetched token's response if it still fits this connection, else null. */
  const takePrefetched = useCallback(
    (fen: string | undefined, sessionId: string | null | undefined): Promise<Response> | null => {
      const current = prefetchedRef.current;
      prefetchedRef.current = null;
      if (!current || current.fen !== fen || Date.now() - current.at >= PREFETCH_REUSE_MS) return null;
      // Minted without a session: fine for a brand-new one (nothing to recap yet).
      if (current.sessionId && current.sessionId !== (sessionId ?? null)) return null;
      return current.response;
    },
    [],
  );

  // Open a Live session. Pass a resumption handle to resume a dropped session
  // (fresh token, same conversation state) instead of starting a new one.
  const openConnection = useCallback(
    async (resumeHandle?: string) => {
      // Mic + AudioContexts first, BEFORE the token fetch and WS connect, so
      // the user-activation window is still open when getUserMedia runs.
      // Idempotent: on a reconnect this reuses the live stream/contexts.
      await acquireMedia();

      // First open of this session (vs. a mid-session reconnect) — only then do
      // we seed the minutes countdown from the mint response.
      const isFirstOpen = sessionStartRef.current === null;

      const fen = optionsRef.current.getFen?.();
      const sessionId = optionsRef.current.getSessionId?.();
      const tokenStart = performance.now();
      const early = resumeHandle ? null : takePrefetched(fen, sessionId);
      let res = early ? await early.catch(() => null) : null;
      if (!res || !res.ok) {
        res = await requestToken(fen, sessionId, resumeHandle);
      }
      if (!res.ok) {
        // Voice minutes exhausted — surface as quota, not a connection error, so
        // the caller can show the "minutes used up" message.
        if (res.status === 429) {
          const detail = await res.json().catch(() => ({}));
          if ((detail as { error?: string })?.error === 'voice_quota_exhausted') {
            const quotaErr = new Error('voice_quota_exhausted');
            (quotaErr as Error & { code?: string }).code = 'voice_quota_exhausted';
            throw quotaErr;
          }
        }
        throw new Error(`Live coach unavailable (${res.status})`);
      }
      const { token, model, promptBytes, remainingSeconds: mintedRemaining, transcription } =
        (await res.json()) as {
          token?: string;
          model?: string;
          promptBytes?: number;
          remainingSeconds?: number | null;
          transcription?: Record<string, unknown>;
        };
      const tokenMs = Math.round(performance.now() - tokenStart);
      if (!token || !model) {
        throw new Error('Invalid live-token response');
      }
      modelRef.current = model;

      // Seed the local minutes countdown from the mint response (first open only;
      // a reconnect keeps the original countdown anchored to the session start).
      if (isFirstOpen && typeof mintedRemaining === 'number') {
        quotaInitialRef.current = mintedRemaining;
        setRemainingSeconds(mintedRemaining);
      }

      const ai = new GoogleGenAI({
        apiKey: token,
        httpOptions: { apiVersion: 'v1alpha' },
      });

      const config: Record<string, unknown> = {
        responseModalities: [Modality.AUDIO],
        // Language hints and chess words for speech recognition, as the token has them.
        inputAudioTranscription: transcription && typeof transcription === 'object' ? transcription : {},
        outputAudioTranscription: {},
      };
      if (resumeHandle) {
        config.sessionResumption = { handle: resumeHandle };
      }

      // Tag this connection; later teardown bumps the counter so a stale
      // session's close/error callback can't trigger a spurious reconnect.
      connGenRef.current += 1;
      const gen = connGenRef.current;

      const connectStart = performance.now();
      const session = await ai.live.connect({
        model,
        callbacks: {
          onmessage: handleMessage,
          onerror: (e: ErrorEvent) => {
            if (gen !== connGenRef.current) return;
            handleDropRef.current(e?.message || 'Live connection error');
          },
          onclose: () => {
            if (gen !== connGenRef.current) return;
            handleDropRef.current();
          },
        },
        config,
      });
      const connectMs = Math.round(performance.now() - connectStart);
      sessionRef.current = session;
      // Anchor session start for the 'end' duration beacon. Only set on the
      // first successful open so a mid-session reconnect keeps the original
      // start (session_ms reflects the whole conversation, not the last leg).
      if (sessionStartRef.current === null) {
        sessionStartRef.current = performance.now();
      }

      // Record connect-phase latency (token mint + WebSocket setup). Off the
      // hot path — a fresh turn's TTFA is measured separately. A resume handle
      // means this is a mid-session auto-reconnect, logged distinctly.
      reportMetric({
        event: resumeHandle ? 'reconnect' : 'connect',
        token_ms: tokenMs,
        connect_ms: connectMs,
        prompt_bytes: typeof promptBytes === 'number' ? promptBytes : undefined,
      });

      // Anchor the initial position client-side so the coach is never blind to it,
      // regardless of whether the token's system instruction carried the FEN.
      if (fen) {
        sendPosition(session, fen);
      }

      await wireCapture(session);

      setIsActive(true);
      setStatus('listening');

      // After a stretch of healthy uptime, restore the one-shot reconnect budget
      // so a later, unrelated drop can still auto-recover. Tied to this conn gen.
      if (healthyTimerRef.current) clearTimeout(healthyTimerRef.current);
      healthyTimerRef.current = setTimeout(() => {
        if (gen === connGenRef.current) {
          reconnectUsedRef.current = false;
        }
      }, HEALTHY_RECONNECT_RESET_MS);

      // Start the metering/countdown heartbeat (cleared in cleanup on any drop).
      stopHeartbeat();
      heartbeatTimerRef.current = setInterval(
        heartbeatTick,
        VOICE_HEARTBEAT_INTERVAL_MS,
      );
    },
    [
      handleMessage,
      acquireMedia,
      wireCapture,
      sendPosition,
      setStatus,
      reportMetric,
      stopHeartbeat,
      heartbeatTick,
      requestToken,
      takePrefetched,
    ],
  );

  // React to a session drop: reconnect ONCE with the stored handle if the drop
  // was unexpected; otherwise surface a terminal error state (deliberate stops
  // and already-surfaced errors are filtered out at the top).
  const handleDrop = useCallback(
    (errMsg?: string) => {
      if (userStoppedRef.current) return; // deliberate stop, handled by disconnect()
      if (statusRef.current === 'error') return; // already surfaced a failure

      const canReconnect =
        !reconnectUsedRef.current && !!resumptionHandleRef.current;
      if (canReconnect) {
        reconnectUsedRef.current = true;
        const handle = resumptionHandleRef.current as string;
        // Tear down the stale session + audio graph but KEEP the mic stream and
        // AudioContexts alive: reacquiring them off-gesture would fail on mobile
        // Safari. openConnection() re-resumes and re-wires them.
        cleanup({ keepMedia: true });
        setStatus('connecting');
        openConnection(handle).catch((err) => {
          if (
            err instanceof Error &&
            (err as Error & { code?: string }).code === 'voice_quota_exhausted'
          ) {
            endForQuotaRef.current();
            return;
          }
          fail(describeError(err, 'Failed to resume live coach'));
        });
        return;
      }

      // No handle (or reconnect already used): terminal. Deliberate stops and
      // already-surfaced errors returned at the top, so reaching here means an
      // unexpected drop we can't recover — surface it instead of going silently
      // idle, so the UI can prompt the user to restart. Mark the lifecycle end
      // as a 'drop' before fail() (whose emitSessionEnd('error') then no-ops).
      emitSessionEnd('drop');
      fail(errMsg ?? 'Live coach disconnected. Please restart to continue.');
    },
    [cleanup, fail, setStatus, openConnection, emitSessionEnd],
  );
  handleDropRef.current = handleDrop;

  // Grab the mic + AudioContexts synchronously-first inside the user gesture,
  // before any network work (session create, token mint). Front-loading this is
  // what fixes mobile Safari: getUserMedia must run while user-activation is
  // still live. connect() re-acquires idempotently, so callers may skip this.
  const prepare = useCallback(async () => {
    if (sessionRef.current) return;
    setError(null);
    setStatus('connecting');
    try {
      await acquireMedia();
    } catch (err) {
      fail(describeError(err, 'Microphone access is required for voice mode'));
      throw err;
    }
  }, [acquireMedia, fail, setStatus]);

  const connect = useCallback(async () => {
    if (sessionRef.current) return;
    setError(null);
    setStatus('connecting');
    // Fresh user-initiated session: reset resumption/reconnect state.
    userStoppedRef.current = false;
    reconnectUsedRef.current = false;
    resumptionHandleRef.current = null;
    // Reset latency instrumentation for the new session.
    turnRef.current = 0;
    lastUserSpeechAtRef.current = null;
    firstAudioPendingRef.current = true;
    // Reset voice-minutes metering for the new session.
    quotaInitialRef.current = null;
    bookedSecondsRef.current = 0;
    setRemainingSeconds(null);

    const isQuota = (err: unknown) =>
      err instanceof Error && (err as Error & { code?: string }).code === 'voice_quota_exhausted';
    try {
      await openConnection();
    } catch (err) {
      // Quota exhausted at mint: end gracefully with the "minutes used up"
      // message instead of a generic connection error.
      if (isQuota(err)) {
        endForQuotaRef.current();
        return;
      }
      // A token mint or a connect that failed once (a transient 5xx, a dropped
      // socket) is tried once more before the student sees an error — the text
      // coach has a fallback model for the same reason.
      if (!userStoppedRef.current) {
        await new Promise((r) => setTimeout(r, START_RETRY_DELAY_MS));
        if (!userStoppedRef.current) {
          try {
            cleanup({ keepMedia: true });
            setStatus('connecting');
            await openConnection();
            return;
          } catch (err2) {
            if (isQuota(err2)) {
              endForQuotaRef.current();
              return;
            }
            err = err2;
          }
        }
      }
      // If the mic was granted but connect failed, fail() -> cleanup() stops the
      // held tracks so no mic indicator lingers.
      fail(describeError(err, 'Голосовой тренер сейчас недоступен — продолжайте текстом, я отвечу здесь.'));
    }
  }, [setStatus, openConnection, fail, cleanup]);

  const disconnect = useCallback(
    (reason: SessionEndReason = 'user_stop') => {
      userStoppedRef.current = true;
      // Guard: a caller wiring disconnect straight to onClick would pass an event
      // here — coerce anything but a known reason back to 'user_stop'.
      const endReason: SessionEndReason =
        reason === 'quota_exhausted' || reason === 'error' || reason === 'drop'
          ? reason
          : 'user_stop';
      // Session-end telemetry (metering 'end' + lifecycle 'session_end'). No-op
      // when no session actually opened.
      emitSessionEnd(endReason);
      cleanup();
      setIsActive(false);
      setRemainingSeconds(null);
      setStatus('idle');
    },
    [cleanup, setStatus, emitSessionEnd],
  );

  // Gracefully end a session because the monthly voice quota ran out. Notify the
  // caller (for the "minutes used up" message) then tear down like a normal stop,
  // tagging the lifecycle end reason as quota exhaustion.
  endForQuotaRef.current = () => {
    optionsRef.current.onQuotaExhausted?.();
    disconnect('quota_exhausted');
  };

  // Push the current board position into the open session mid-conversation.
  // turnComplete:false injects context without interrupting the audio turn.
  const sendBoardUpdate = useCallback(
    (fen: string) => {
      const session = sessionRef.current;
      if (!session || !fen || fen === boardFenRef.current) return;
      sendPosition(session, fen);
    },
    [sendPosition],
  );

  // Ensure resources are released on unmount.
  useEffect(() => {
    return () => {
      cleanup();
    };
  }, [cleanup]);

  return {
    status,
    isSupported,
    isActive,
    error,
    prepare,
    connect,
    prefetch,
    disconnect,
    sendBoardUpdate,
    remainingSeconds,
  };
}
