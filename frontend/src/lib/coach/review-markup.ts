/**
 * Inline board marks in a Review Coach explanation.
 *
 * The coach writes arrows and highlights inside its text:
 *
 *     [[arrows: c6d4 green, d4e2 red]]   [[squares: d4 e5]]
 *
 * Hermes cuts them out of new answers and sends `board_actions` frames instead
 * (hermes/src/board_markup.py), but explanations cached before that fix still
 * carry them raw (production, 2026-10-21). This parser is the client-side twin:
 * it turns marks into board shapes and drops them from the text. The hook also
 * stores a streamed answer's board actions back as one trailing mark, so the
 * cache keeps a single string per explanation.
 */

export interface CoachArrow {
  from: string;
  to: string;
  brush: string;
}

export interface ParsedCoachText {
  text: string;
  arrows: CoachArrow[];
  squares: string[];
}

const MARK = /\[\[\s*([\s\S]*?)\s*\]\]/g;
const KIND = /^(arrows?|squares?|highlights?)\b\s*:?\s*/i;
const COLOR_ONLY = /^(?:green|red|blue|yellow)$/i;
const ARROW = /\b([a-h][1-8])\s*(?:->|-|–|—|>)?\s*([a-h][1-8])\b(?:\s*\(?\s*(green|red|blue|yellow)\b)?/gi;
const SQUARE = /\b([a-h][1-8])\b/gi;
/** A bare [[…]] (no "arrows:" / "squares:") is a mark only when it is this short. */
const BARE_MAX = 40;
/** An opened "[[" that has not closed within this many characters is not a mark. */
const MAX_MARK_CHARS = 400;

type Kind = 'arrows' | 'squares' | 'drop' | null;

function kindOf(body: string): { kind: Kind; rest: string } {
  const k = KIND.exec(body);
  if (k) {
    const word = k[1].toLowerCase();
    return { kind: word.startsWith('arrow') ? 'arrows' : 'squares', rest: body.slice(k[0].length) };
  }
  if (COLOR_ONLY.test(body.trim())) return { kind: 'drop', rest: '' };
  if (body.length <= BARE_MAX && new RegExp(ARROW.source, 'i').test(body)) return { kind: 'arrows', rest: body };
  if (body.length <= BARE_MAX && new RegExp(SQUARE.source, 'i').test(body)) return { kind: 'squares', rest: body };
  return { kind: null, rest: body };
}

/** Tidy the gaps a cut mark leaves: " ." → ".", double spaces, a sentence opening on "." */
function tidy(text: string): string {
  return text
    .replace(/[ \t]+([.,;:!?)])/g, '$1')
    .replace(/[ \t]{2,}/g, ' ')
    .replace(/(^|\n)[ \t]*[.,;:]+[ \t]*/g, '$1')
    .trim();
}

/** Split explanation text into clean prose plus the arrows/squares its marks draw. */
export function parseCoachMarkup(raw: string): ParsedCoachText {
  const arrows: CoachArrow[] = [];
  const squares: string[] = [];
  let found = false;

  let text = raw.replace(MARK, (whole, body: string) => {
    const { kind, rest } = kindOf(body);
    if (kind === null) return whole; // some other [[...]]: leave it in the text
    found = true;
    if (kind === 'arrows') {
      for (const m of rest.matchAll(ARROW)) {
        const from = m[1].toLowerCase();
        const to = m[2].toLowerCase();
        if (from === to) continue;
        const arrow = { from, to, brush: (m[3] ?? 'green').toLowerCase() };
        if (!arrows.some((a) => a.from === from && a.to === to && a.brush === arrow.brush)) arrows.push(arrow);
      }
    } else if (kind === 'squares') {
      for (const m of rest.matchAll(SQUARE)) {
        const sq = m[1].toLowerCase();
        if (!squares.includes(sq)) squares.push(sq);
      }
    }
    return ' ';
  });

  // While streaming, an unfinished trailing mark is held back rather than shown.
  const open = text.lastIndexOf('[[');
  if (open >= 0 && !text.includes(']]', open) && text.length - open <= MAX_MARK_CHARS) {
    text = text.slice(0, open);
    found = true;
  }

  return { text: found ? tidy(text) : raw, arrows, squares };
}

/** The board actions of a streamed answer, written back as marks (for the cache). */
export function marksFor(arrows: CoachArrow[], squares: string[]): string {
  const parts: string[] = [];
  if (arrows.length) parts.push(`[[arrows: ${arrows.map((a) => `${a.from}${a.to} ${a.brush}`).join(', ')}]]`);
  if (squares.length) parts.push(`[[squares: ${squares.join(' ')}]]`);
  return parts.join(' ');
}
