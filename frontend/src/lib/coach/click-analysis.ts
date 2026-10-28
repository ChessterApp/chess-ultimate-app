/**
 * Click-analysis requests of /position, /game, /puzzle («разобрать ход
 * дебюта / линию движка / кандидата / ход в разборе / аннотацию»).
 *
 * Hermes caps `query` at 2000 characters (hermes/src/server.py
 * _validate_analysis_body). The page used to glue master stats, ChessDB
 * candidates and every engine line onto the query, so with master stats each
 * click got 400 «Query too long» (28.10). The request now goes in `query` and
 * the grounding in `context_note`, which Hermes gives the model for this turn
 * only (cap ANALYSIS_CONTEXT_MAX).
 */
import { Chess } from 'chess.js';
import type { Moves, MasterGames } from '@/lib/openingdatabase/helper';
import type { CandidateMove } from '@/components/tabs/Chessdb';
import type { MoveAnalysis } from '@/hooks/useGameReview';
import { parseCoachMarkup, type CoachArrow } from '@/lib/coach/review-markup';

/** Hermes' query cap (server.py _validate_analysis_body). */
export const ANALYSIS_QUERY_MAX = 2000;
/** Hermes' context_note cap (server.py ANALYSIS_CONTEXT_MAX). */
export const ANALYSIS_CONTEXT_MAX = 12000;

export type ClickAnalysisType =
  | 'engineLine'
  | 'openingMove'
  | 'candidateMove'
  | 'moveCoach'
  | 'annotation';

/** The grounding the page has for the position (already rendered to text). */
export interface AnalysisGrounding {
  openingSpeech?: string | null;
  databaseSpeech?: string | null;
  /** Body of <engine_analysis>: "Depth: N" plus the formatted lines. */
  engineAnalysis?: string | null;
}

export interface ClickAnalysisInput {
  type: ClickAnalysisType;
  currentFen: string;
  /** engineLine: the clicked line, formatted (formatLineForLLM). */
  engineLineText?: string;
  /** openingMove: the clicked explorer move and the position's opening. */
  move?: Moves;
  openingData?: MasterGames | null;
  /** candidateMove: the clicked ChessDB move. */
  candidate?: CandidateMove;
  /** moveCoach / annotation: the reviewed move. */
  review?: MoveAnalysis;
  /** annotation: the student's own note from the PGN view. */
  customQuery?: string;
  grounding: AnalysisGrounding;
}

export interface AnalysisRequest {
  fen: string;
  query: string;
  context_note?: string;
}

function sideOf(fen: string): string {
  return new Chess(fen).turn() === 'w' ? 'White' : 'Black';
}

/** The grounding blocks as one note, never over Hermes' cap. */
export function buildAnalysisContextNote(g: AnalysisGrounding): string | undefined {
  const blocks: string[] = [];
  if (g.openingSpeech) blocks.push(`<opening_information>\n${g.openingSpeech}\n</opening_information>`);
  if (g.databaseSpeech) blocks.push(`<database_analysis>\n${g.databaseSpeech}\n</database_analysis>`);
  if (g.engineAnalysis) blocks.push(`<engine_analysis>\n${g.engineAnalysis}\n</engine_analysis>`);
  if (!blocks.length) return undefined;
  const open = '<analysis_context>\n';
  const close = '\n</analysis_context>';
  let body = blocks.join('\n\n');
  const room = ANALYSIS_CONTEXT_MAX - open.length - close.length;
  if (body.length > room) body = body.slice(0, room - 1) + '…';
  return open + body + close;
}

/**
 * The grounding goes inside the query when the whole fits Hermes' query cap — as before 28.10, so an older Hermes
 * (which drops context_note without a word) still gets the engine lines; only a request over the cap, which an older
 * Hermes rejected anyway, carries it in context_note (review 28.10: no silent loss during the rollout).
 */
export function packAnalysisRequest(fen: string, query: string, note: string | undefined): AnalysisRequest {
  if (!note) return { fen, query };
  const inline = `${query}\n\n${note}`;
  return inline.length <= ANALYSIS_QUERY_MAX ? { fen, query: inline } : { fen, query, context_note: note };
}

/** Append the student's note, cut so the query stays under Hermes' cap. */
function withCustomQuery(base: string, closing: string, customQuery?: string): string {
  const note = customQuery?.trim();
  if (!note) return `${base}\n${closing}`;
  const open = '\n\n<additional_considerations>\n';
  const shut = '\n</additional_considerations>\n';
  const room = ANALYSIS_QUERY_MAX - base.length - open.length - shut.length - closing.length;
  const fitted = note.length > room ? note.slice(0, Math.max(0, room - 1)) + '…' : note;
  return room > 0 ? `${base}${open}${fitted}${shut}${closing}` : `${base}\n${closing}`;
}

/** The query (the request itself) and the context note for one click. */
export function buildClickAnalysisRequest(input: ClickAnalysisInput): AnalysisRequest {
  const { type, currentFen } = input;
  let fen = currentFen;
  let base = '';

  switch (type) {
    case 'engineLine': {
      base = `<chess_analysis_request>

<analysis_type>Engine Line Analysis</analysis_type>

<position_context>
Current FEN: ${currentFen}
Side to Move: ${sideOf(currentFen)}
</position_context>

<engine_line>
${input.engineLineText ?? ''}
</engine_line>

<analysis_instructions>
Please follow this structure in your analysis:
1. First, describe the board state and key features of the position before the move (pawn structure, piece activity, king safety, imbalances, threats, etc).
2. Next, analyze the move itself: what does it change in the position, and what are its immediate tactical or strategic consequences?
3. Then, consider the engine lines and candidate moves: what alternatives were available, and how do they compare to the move played?
4. Take account of 1, 2, 3 and provide the analysis for this engine line.

Be concise but thorough, and use clear chess language.
</analysis_instructions>`;
      break;
    }
    case 'openingMove': {
      const move = input.move!;
      const totalGames = (move.white ?? 0) + (move.draws ?? 0) + (move.black ?? 0);
      const whiteWinRate = ((move.white / totalGames) * 100 || 0).toFixed(1);
      const drawRate = ((move.draws / totalGames) * 100 || 0).toFixed(1);
      const blackWinRate = ((move.black / totalGames) * 100 || 0).toFixed(1);
      base = `<chess_analysis_request>

<analysis_type>Opening Move Analysis</analysis_type>

<position_context>
Current FEN: ${currentFen}
Opening: ${input.openingData?.opening?.name || 'Unknown'} (${input.openingData?.opening?.eco || 'N/A'})
Side to Move: ${sideOf(currentFen)}
</position_context>

<move_information>
Move: ${move.san}
Games played: ${totalGames}
Average rating: ${move.averageRating}
White wins: ${whiteWinRate}%
Draws: ${drawRate}%
Black wins: ${blackWinRate}%
</move_information>

<analysis_instructions>
Please follow this structure in your analysis:
1. First, describe the board state and key features of the position before the move (pawn structure, piece activity, king safety, imbalances, threats, etc).
2. Next, analyze the move itself: what does it change in the position, and what are its immediate tactical or strategic consequences?
3. Then, understand the opening stats, the win, draw, loss rates and amount of games that were played by masters.
4. Then, consider the engine lines and candidate moves: what alternatives were available, and how do they compare to the move played?
5. Take account of 1, 2, 3, 4 and provide the analysis for this move.

Be concise but thorough, and use clear chess language.
</analysis_instructions>`;
      break;
    }
    case 'candidateMove': {
      const c = input.candidate!;
      base = `<chess_analysis_request>

<analysis_type>Candidate Move Analysis</analysis_type>

<position_context>
Current FEN: ${currentFen}
Side to Move: ${sideOf(currentFen)}
</position_context>

<move_information>
Move: ${c.san} (${c.uci})
ChessDb Score: ${c.score}
ChessDb Winrate: ${c.winrate}
</move_information>

<analysis_instructions>
Please follow this structure in your analysis:
1. First, understand and describe the board state and key features of the position before the move (pawn structure, piece activity, king safety, imbalances, threats, etc).
2. Next, analyze the move itself: what does it change in the position, and what are its immediate tactical or strategic consequences?
3. Then, consider the engine lines and candidate moves: what alternatives were available, and how do they compare to the move played?
4. Take account of 1, 2, 3 and provide analysis of the candidate move and how it impacts the position.

Be concise but thorough, and use clear chess language.
</analysis_instructions>`;
      break;
    }
    case 'moveCoach': {
      const r = input.review!;
      const side = r.player === 'w' ? 'White' : 'Black';
      const moveNumber = Math.floor(r.plyNumber / 2) + 1;
      const notation = r.plyNumber % 2 === 0 ? `${moveNumber}.` : `${moveNumber}...`;
      base = `<chess_analysis_request>

<analysis_type>Move Coach Analysis</analysis_type>

<position_context>
Position FEN: ${r.fen}
Side: ${side}
</position_context>

<move_information>
Move: ${notation} ${r.notation}
Classification: ${r.quality}
Player: ${side}
Ply Number: ${r.plyNumber}
</move_information>

<analysis_instructions>
As a chess buddy, please follow this structure in your analysis:
1. First, understand and describe the board state and key features of the position before the move (pawn structure, piece activity, king safety, imbalances, threats, etc).
2. Next, analyze the move itself: what does it change in the position, and what are its immediate tactical or strategic consequences?
3. Then, consider the engine lines and candidate moves: what alternatives were available, and how do they compare to the move played?
4. Take account of 1, 2, 3 and explain why this move is classified as a ${r.quality} move.

Be concise but thorough, and use clear chess language.
</analysis_instructions>`;
      fen = r.fen;
      break;
    }
    case 'annotation': {
      const r = input.review!;
      const side = r.player === 'w' ? 'White' : 'Black';
      const moveNumber = Math.floor(r.plyNumber / 2) + 1;
      const notation = r.plyNumber % 2 === 0 ? `${moveNumber}.` : `${moveNumber}...`;
      base = `<chess_annotation_request>

<analysis_type>Move Annotation</analysis_type>

<position_context>
Position FEN: ${r.fen}
Current FEN: ${currentFen}
Side: ${side}
</position_context>

<move_information>
Move: ${r.notation}
Classification: ${r.quality}
Move Number: ${notation}
</move_information>

<annotation_instructions>
Please provide annotation about this move:
1. Talk about how/why the move is ${r.quality} based on the NEXT ply engine analysis
2. Talk about candidates in this position using the CURRENT ply engine analysis
3. How the move can impact the game
4. Keep the response in paragraph format

Start the response with "Chesster Annotation:"
</annotation_instructions>`;
      fen = r.fen;
      break;
    }
  }

  const closing = type === 'annotation' ? '</chess_annotation_request>' : '</chess_analysis_request>';
  const query = withCustomQuery(base, closing, input.customQuery);
  return packAnalysisRequest(fen, query, buildAnalysisContextNote(input.grounding));
}

/** «Разобрать ход» from the legal-moves list: the position after the move. */
export function buildFutureMoveRequest(
  move: string,
  futureFen: string,
  grounding: AnalysisGrounding,
): AnalysisRequest {
  const query = `Analyze the chess move ${move} in this position:

Position: ${futureFen}
Side To Move: ${sideOf(futureFen)}

Please follow this structure in your analysis:
1. First, understand and describe the board state and key features of the position before the move
2. Next, analyze the move itself: what does it change in the position
3. Then, consider the engine lines and candidate moves: what alternatives were available
4. Take account of 1, 2, 3 and provide analysis of the candidate move and how it impacts the position

Be concise but thorough, and use clear chess language.

Analyze this move from different points of view.`;
  return packAnalysisRequest(futureFen, query, buildAnalysisContextNote(grounding));
}

/** The arrows of Hermes' board_actions (each draw_arrows carries all so far). */
export function arrowsFromBoardActions(actions: unknown): CoachArrow[] {
  if (!Array.isArray(actions)) return [];
  let arrows: CoachArrow[] = [];
  for (const a of actions) {
    if (a && typeof a === 'object' && (a as { type?: unknown }).type === 'draw_arrows') {
      const list = (a as { arrows?: unknown }).arrows;
      if (Array.isArray(list)) {
        arrows = list
          .filter(
            (x): x is { from: string; to: string; brush?: string } =>
              !!x && typeof x.from === 'string' && typeof x.to === 'string',
          )
          .map((x) => ({ from: x.from, to: x.to, brush: x.brush || 'green' }));
      }
    }
  }
  return arrows;
}

/** The coach's arrows and the positions they are drawn on. */
export interface CoachArrowsOnBoard {
  /** The position the board showed when the student asked: the arrows go there. */
  fen: string;
  /** The position the answer is about, if another one (the move's position): drawn there too. */
  about?: string;
  arrows: CoachArrow[];
}

/**
 * Where an answer's arrows go. They were kept only under the request's FEN, which for «Analyze move» is the position
 * after the move and for the review clicks the one before it — positions the board was not showing, so the arrows the
 * coach promised never appeared (review 28.10). The board the student asked from is what they look at.
 */
export function placeCoachArrows(
  arrows: CoachArrow[],
  boardFen: string | null | undefined,
  requestFen: string,
): CoachArrowsOnBoard | null {
  if (!arrows.length) return null;
  if (!boardFen || samePosition(boardFen, requestFen)) return { fen: requestFen, arrows };
  // Shown on the board's position only when it is one move from the analysed one (the move being analysed: before
  // or after it). Any other position — an «Annotate with AI» on a far move, the game report looping over key moves —
  // keeps them on their own position, drawn when the board gets there (review 28.10).
  if (!oneMoveApart(boardFen, requestFen)) return { fen: requestFen, arrows };
  return { fen: boardFen, about: requestFen, arrows };
}

function oneMoveApart(a: string, b: string): boolean {
  const reaches = (from: string, to: string) => {
    try {
      const target = to.split(' ')[0];
      return new Chess(from).moves({ verbose: true }).some((m) => m.after.split(' ')[0] === target);
    } catch {
      return false;
    }
  };
  return reaches(a, b) || reaches(b, a);
}

export interface AnalysisReply {
  message: string;
  maxTokens: number;
  arrows: CoachArrow[];
}

/**
 * The non-streaming /api/coach/analysis answer as the page shows it: clean
 * text plus the arrows to draw. Marks are also cut here — a Hermes older than
 * 28.10 sends them raw. Hermes sends no model/provider/timing, so none are
 * invented (the page showed a made-up «claude-3-5-sonnet» and its price).
 */
export function readAnalysisReply(data: {
  response?: unknown;
  tokens_used?: unknown;
  board_actions?: unknown;
}): AnalysisReply {
  const raw = typeof data.response === 'string' ? data.response : '';
  const parsed = parseCoachMarkup(raw);
  const fromActions = arrowsFromBoardActions(data.board_actions);
  const arrows = [...fromActions];
  for (const a of parsed.arrows) {
    if (!arrows.some((b) => b.from === a.from && b.to === a.to)) arrows.push(a);
  }
  return {
    message: parsed.text,
    maxTokens: typeof data.tokens_used === 'number' ? data.tokens_used : 0,
    arrows,
  };
}

/** A proxy's context_note: a non-empty string or nothing (Hermes 400s on a non-string). */
export function contextNoteOf(v: unknown): string | undefined {
  return typeof v === 'string' && v.trim() ? v : undefined;
}

/** Do two FENs show the same position (placement and side to move)? */
export function samePosition(a: string | null | undefined, b: string | null | undefined): boolean {
  if (!a || !b) return false;
  const [pa, sa] = a.trim().split(/\s+/);
  const [pb, sb] = b.trim().split(/\s+/);
  return pa === pb && (sa ?? 'w') === (sb ?? 'w');
}

/** The coach's arrows the board draws while it shows `boardFen` (none on another position). */
export function coachArrowsFor(coach: CoachArrowsOnBoard | null | undefined, boardFen: string | null | undefined): CoachArrow[] {
  if (!coach) return [];
  return samePosition(coach.fen, boardFen) || samePosition(coach.about, boardFen) ? coach.arrows : [];
}
