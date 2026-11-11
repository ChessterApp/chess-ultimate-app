/**
 * What the voice coach must never say aloud, and the student must never read as its words: the system's own
 * records — a note tag in square brackets («[Board] …», «[Engine] …», «[Диаграмма: …]»), a position record (FEN),
 * a tool call written out («board_control(set_fen…)»).
 *
 * Alexander's phone, 10.11: asked «не вижу», the Live coach said «Секунду, сейчас всё исправлю. [Board] …» and read
 * a position record aloud («e1 … пи-пи-пи» — the pawns of a FEN); the board did not change, because saying a record
 * changes nothing. The chat's old filter knew six tag names and only took the tag itself out.
 *
 * One rule for both voice modes:
 *  - Live (the model speaks itself): the moment its words contain such a record, the rest of the turn is never
 *    heard nor shown, and the model is told that the board changes only through a tool (src/hooks/useGeminiLive.ts);
 *  - the pipeline (the text coach read aloud): such records are taken out of what is read (voice-pipeline.speakable).
 * A record is never executed as a board action: a position a model writes out by hand is exactly what the coach is
 * not allowed to put up (Hermes' src/board_truth.py); the model is sent to the tools that put a verified one.
 */

export type NoteLeakKind = 'tag' | 'fen' | 'tool' | 'echo';
export interface NoteLeak {
  /** Where the record starts in the text. */
  index: number;
  kind: NoteLeakKind;
}

const LETTERS = 'A-Za-zА-Яа-яЁёӘәІіҢңҒғҮүҰұҚқӨөҺһ';
// «[Board]», «[Engine]», «[Диаграмма: 8/8…», «[Картинка учебника: …»: a bracket, one to three words, then «]» or «:».
// A move in brackets («[e4]») has a digit and is not one.
const TAG_SRC = `\\[\\s*[${LETTERS}]{2,20}(?:[ \\t]+[${LETTERS}]{2,20}){0,2}\\s*(?:\\]|:)`;
// Four or more ranks of a position record: «rnbqkbnr/pppppppp/8/8/…».
const FEN_SRC = '(?:[pnbrqkPNBRQK1-8]{1,8}/){3,}[pnbrqkPNBRQK1-8]{1,8}(?:\\s+[wb](?=\\s|$)(?:\\s+(?:[KQkq]{1,4}|-)(?:\\s+(?:[a-h][36]|-)(?:\\s+\\d+\\s+\\d+)?)?)?)?';
// A tool or an argument by its name (snake_case is never a spoken word), a call written as code or JSON.
const TOOL_SRC = '(?<![A-Za-z0-9_])[a-z]{2,}(?:_[a-z0-9]+)+(?![A-Za-z0-9_])(?:\\s*\\([^)\\n]{0,200}\\))?|```|\\{\\s*"[A-Za-z_]+"\\s*:|\\bfunctionCalls?\\b';
// The site's own line about the board, said back.
const ECHO_SRC = 'Current position \\(FEN\\)\\s*:?';

const LEAKS: Array<[NoteLeakKind, RegExp]> = [
  ['tag', new RegExp(TAG_SRC)],
  ['fen', new RegExp(FEN_SRC)],
  ['tool', new RegExp(TOOL_SRC)],
  ['echo', new RegExp(ECHO_SRC, 'i')],
];

/** The first system record in the coach's words, or null. */
export function noteLeak(text: string): NoteLeak | null {
  let found: NoteLeak | null = null;
  for (const [kind, re] of LEAKS) {
    const m = re.exec(text);
    if (m && (found === null || m.index < found.index)) found = { index: m.index, kind };
  }
  return found;
}

/** A text without its system records (the rest is kept): what the pipeline may read aloud. */
export function stripNotes(text: string): string {
  return text
    .replace(new RegExp(`\\[\\s*[${LETTERS}]{2,20}(?:[ \\t]+[${LETTERS}]{2,20}){0,2}\\s*(?::[^\\]\\n]{0,200})?\\]`, 'g'), ' ')
    .replace(new RegExp(ECHO_SRC, 'gi'), ' ')
    .replace(new RegExp(FEN_SRC, 'g'), ' ')
    .replace(new RegExp(TOOL_SRC, 'g'), ' ');
}

/**
 * The Live coach's words as the chat shows them: without a system record in them, and without a bracket still
 * open at the end (a tag arriving in pieces). What follows a record is cut by the hook, which stops the turn there;
 * words that were heard all the same (the cut switched off, an older page's cache) stay.
 */
export function shownText(text: string): string {
  const open = text.lastIndexOf('[');
  const whole = open >= 0 && text.indexOf(']', open) < 0 && text.length - open <= 48 ? text.slice(0, open) : text;
  if (whole === text && noteLeak(text) === null) return text;
  return stripNotes(whole).replace(/[ \t]{2,}/g, ' ').replace(/^[ \t]+/, '').replace(/[ \t]+$/, '');
}

const START_BOARD = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR';

/** The board in a note's words: «the starting position», «an empty board», or its FEN. */
export function boardInWords(fen: string | undefined | null): string {
  const placement = (fen ?? '').split(' ')[0];
  if (!placement) return 'the same position as before';
  if (placement === START_BOARD) return 'the starting position';
  if (placement === '8/8/8/8/8/8/8/8') return 'an empty board';
  return `the position ${fen}`;
}

/** What the Live coach is told when it began to say a system record aloud: its turn was cut there. */
export function leakNote(fen: string | undefined | null): string {
  return (
    '[Voice] You began to read a system record aloud (a tag in square brackets, a position record or a tool name): ' +
    'the student heard noise, and it was cut off. Saying a record changes NOTHING: the board still shows ' +
    `${boardInWords(fen)}. The board changes only through a tool call. If you promised to show a position, call the ` +
    'tool now — get_topic or get_lesson for an example of a concept, board_control load_pgn for moves — and speak about ' +
    'it only after the result says it is on the board. Otherwise say one short sentence of apology and go on in words. ' +
    'Never say a tag, a FEN or a tool name aloud.'
  ).replace(/\s+/g, ' ').trim();
}

/** What the Live coach is told when it pointed the student at a position that is not on the board (Hermes' src/unshown_board.py). */
export function unshownNote(sentence: string, fen: string | undefined | null): string {
  return (
    `[Check] You said «${sentence.trim()}», but nothing of it is on the student's board: it shows ${boardInWords(fen)}, ` +
    'no example was put up, and the student sees none of what you describe — you were stopped there. Do not go on ' +
    'describing it. Say in one short sentence, in the student\'s language, that you will put an example on the board, ' +
    'then call get_topic with the name of the concept (it puts a verified position on the board) and explain only the ' +
    'position its result names. If the result says nothing was put up, explain in words and point at nothing.'
  ).replace(/\s+/g, ' ').trim();
}
