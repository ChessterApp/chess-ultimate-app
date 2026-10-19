/**
 * The lesson tutor's SSE frames (Hermes `/api/lesson/chat`, proxied by `/api/tutor/…/chat`).
 *
 * Besides `delta` text the tutor sends, before its first word, the lesson's diagram the question is
 * about (`diagram`: the programme's own explanatory position — 2026-10-20), so the lesson page draws
 * it beside the answer instead of describing a picture the student cannot see.
 */

export interface TutorDiagram {
  fen: string;
  caption?: string;
  n?: number;
  of?: number;
}

export interface TutorFrame {
  delta?: string;
  diagram?: TutorDiagram;
  error?: string;
  done?: boolean;
}

const FEN_RE = /^[pnbrqkPNBRQK1-8/]+(\s+[wb](\s+\S+){0,4})?$/;

/** One `data: …` line of the tutor stream as a typed frame; null for anything else. */
export function parseTutorFrame(line: string): TutorFrame | null {
  if (!line.startsWith('data: ')) return null;
  let data: unknown;
  try {
    data = JSON.parse(line.slice(6));
  } catch {
    return null;
  }
  if (!data || typeof data !== 'object') return null;
  const src = data as Record<string, unknown>;
  const out: TutorFrame = {};
  if (typeof src.delta === 'string') out.delta = src.delta;
  if (typeof src.error === 'string') out.error = src.error;
  else if (src.error) out.error = String(src.error);
  if (src.done === true) out.done = true;
  const d = src.diagram;
  if (d && typeof d === 'object') {
    const fen = (d as Record<string, unknown>).fen;
    if (typeof fen === 'string' && FEN_RE.test(fen.trim())) {
      const diagram: TutorDiagram = { fen: fen.trim() };
      const caption = (d as Record<string, unknown>).caption;
      if (typeof caption === 'string' && caption.trim()) diagram.caption = caption.trim();
      const n = (d as Record<string, unknown>).n;
      const of = (d as Record<string, unknown>).of;
      if (typeof n === 'number') diagram.n = n;
      if (typeof of === 'number') diagram.of = of;
      out.diagram = diagram;
    }
  }
  return out;
}
