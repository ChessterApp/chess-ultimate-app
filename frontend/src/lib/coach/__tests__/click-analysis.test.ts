import { describe, it, expect } from 'vitest';
import {
  packAnalysisRequest,
  ANALYSIS_CONTEXT_MAX,
  ANALYSIS_QUERY_MAX,
  arrowsFromBoardActions,
  buildClickAnalysisRequest,
  buildFutureMoveRequest,
  readAnalysisReply,
  samePosition,
  placeCoachArrows,
  coachArrowsFor,
  type ClickAnalysisInput,
} from '../click-analysis';

const FEN = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq e3 0 1';
const BIG = {
  openingSpeech: 'Move 1: e5, played in games with average rating 2400. '.repeat(60),
  databaseSpeech: 'Move: e5 Eval 30 WinRate 51 Note: !\n'.repeat(40),
  engineAnalysis: 'Depth: 18\n  Line 1: +0.3\n    Moves: 1... e5 2. Nf3 Nc6 3. Bb5 a6 4. Ba4 Nf6'.repeat(5),
};
const review = {
  plyNumber: 1, notation: 'e5', sanNotation: 'e5', quality: 'Mistake', arrowMove: { from: 'e7', to: 'e5' },
  evalMove: 0, fen: FEN, currenFen: FEN, player: 'b',
} as unknown as ClickAnalysisInput['review'];

const inputs: ClickAnalysisInput[] = [
  { type: 'engineLine', currentFen: FEN, engineLineText: 'Line 1: +0.30 - 1... e5 2. Nf3 Nc6 3. Bb5', grounding: BIG },
  {
    type: 'openingMove', currentFen: FEN, grounding: BIG,
    move: { san: 'e5', uci: 'e7e5', white: 10, draws: 10, black: 10, averageRating: 2400 } as any,
  },
  { type: 'candidateMove', currentFen: FEN, grounding: BIG, candidate: { san: 'e5', uci: 'e7e5', score: '30', winrate: '51', rank: '2', note: '!' } },
  { type: 'moveCoach', currentFen: FEN, grounding: BIG, review },
  { type: 'annotation', currentFen: FEN, grounding: BIG, review, customQuery: 'why not d5? '.repeat(400) },
];

describe('click-analysis request (28.10: 400 «Query too long» on every click with master stats)', () => {
  it.each(inputs.map((i) => [i.type, i] as const))('%s: query fits Hermes, grounding goes in context_note', (_t, input) => {
    const req = buildClickAnalysisRequest(input);
    expect(req.query.length).toBeLessThanOrEqual(ANALYSIS_QUERY_MAX);
    expect(req.query).not.toContain('<opening_information>');
    expect(req.context_note).toContain('<opening_information>');
    expect(req.context_note).toContain('<database_analysis>');
    expect(req.context_note).toContain('<engine_analysis>');
    expect(req.context_note!.length).toBeLessThanOrEqual(ANALYSIS_CONTEXT_MAX);
  });

  it('annotation keeps its own tags and the student note (cut to fit)', () => {
    const req = buildClickAnalysisRequest(inputs[4]);
    expect(req.query.startsWith('<chess_annotation_request>')).toBe(true);
    expect(req.query.trimEnd().endsWith('</chess_annotation_request>')).toBe(true);
    expect(req.query).toContain('<additional_considerations>\nwhy not d5?');
  });

  it('moveCoach / annotation analyse the reviewed position', () => {
    const other = { ...inputs[3], currentFen: '8/8/8/8/8/8/8/K6k w - - 0 1' };
    expect(buildClickAnalysisRequest(other).fen).toBe(FEN);
  });

  it('no grounding → no context_note', () => {
    expect(buildClickAnalysisRequest({ ...inputs[0], grounding: {} }).context_note).toBeUndefined();
  });

  it('a huge grounding is cut to the context cap', () => {
    const req = buildClickAnalysisRequest({ ...inputs[0], grounding: { databaseSpeech: 'x'.repeat(50000) } });
    expect(req.context_note!.length).toBeLessThanOrEqual(ANALYSIS_CONTEXT_MAX);
    expect(req.context_note!.endsWith('</analysis_context>')).toBe(true);
  });

  it('future move: query fits, stats go in context_note', () => {
    const req = buildFutureMoveRequest('e5', FEN, BIG);
    expect(req.query.length).toBeLessThanOrEqual(ANALYSIS_QUERY_MAX);
    expect(req.context_note).toContain('<opening_information>');
  });
});

describe('readAnalysisReply (28.10: raw [[arrows]] in the text, invented model)', () => {
  it('cuts marks a Hermes before 28.10 sends raw, and keeps their arrows', () => {
    const r = readAnalysisReply({ response: 'Push the pawn [[arrows: e2e4 green]]. Good.', tokens_used: 7 });
    expect(r.message).not.toContain('[[');
    expect(r.message).toContain('Push the pawn');
    expect(r.arrows).toEqual([{ from: 'e2', to: 'e4', brush: 'green' }]);
    expect(r.maxTokens).toBe(7);
  });

  it('takes the arrows from board_actions', () => {
    const r = readAnalysisReply({
      response: 'Push the pawn.',
      board_actions: [
        { type: 'draw_arrows', arrows: [{ from: 'e2', to: 'e4', brush: 'green' }] },
        { type: 'highlight_squares', squares: ['e4'], color: 'yellow' },
        { type: 'draw_arrows', arrows: [{ from: 'e2', to: 'e4', brush: 'green' }, { from: 'g1', to: 'f3', brush: 'blue' }] },
      ],
    });
    expect(r.arrows).toEqual([
      { from: 'e2', to: 'e4', brush: 'green' },
      { from: 'g1', to: 'f3', brush: 'blue' },
    ]);
  });

  it('invents no model, provider or timing', () => {
    const r = readAnalysisReply({ response: 'x' }) as unknown as Record<string, unknown>;
    expect(r.model).toBeUndefined();
    expect(r.provider).toBeUndefined();
    expect(r.response_time_ms).toBeUndefined();
  });

  it('arrowsFromBoardActions ignores junk', () => {
    expect(arrowsFromBoardActions(null)).toEqual([]);
    expect(arrowsFromBoardActions([{ type: 'draw_arrows', arrows: [{ from: 1 }] }])).toEqual([]);
  });

  it('samePosition compares placement and side to move only', () => {
    expect(samePosition(FEN, FEN.replace(' 0 1', ' 3 7'))).toBe(true);
    expect(samePosition(FEN, FEN.replace(' b ', ' w '))).toBe(false);
    expect(samePosition(FEN, null)).toBe(false);
  });
});

describe('packAnalysisRequest (review 28.10: no silent loss while an older Hermes drops context_note)', () => {
  const FEN = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';
  it('a request that fits the query cap carries its grounding inside the query, as before', () => {
    const r = packAnalysisRequest(FEN, 'Analyze e4.', '<analysis_context>\nengine: e5 (+0.3)\n</analysis_context>');
    expect(r.context_note).toBeUndefined();
    expect(r.query).toContain('engine: e5 (+0.3)');
  });
  it('only a request over the cap moves the grounding to context_note', () => {
    const r = packAnalysisRequest(FEN, 'Analyze e4.', `<analysis_context>\n${'x'.repeat(2500)}\n</analysis_context>`);
    expect(r.query).toBe('Analyze e4.');
    expect(r.context_note?.length).toBeGreaterThan(2000);
  });
});

describe('placeCoachArrows / coachArrowsFor (review 28.10: arrows on a position the board was not showing)', () => {
  const A = [{ from: 'e7', to: 'e5', brush: 'green' }];
  const BOARD = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
  const ABOUT = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';
  const OTHER = 'rnbqkbnr/pppppppp/8/8/3P4/8/PPP1PPPP/RNBQKBNR b KQkq - 0 1';

  it('drawn on the board the student asked from and on the position the answer is about', () => {
    const placed = placeCoachArrows(A, BOARD, ABOUT);
    expect(coachArrowsFor(placed, BOARD)).toEqual(A);
    expect(coachArrowsFor(placed, ABOUT)).toEqual(A);
    expect(coachArrowsFor(placed, OTHER)).toEqual([]);
  });

  it('nothing to place without arrows; one position when they are the same', () => {
    expect(placeCoachArrows([], BOARD, ABOUT)).toBeNull();
    expect(placeCoachArrows(A, BOARD, BOARD)).toEqual({ fen: BOARD, arrows: A });
  });
});
