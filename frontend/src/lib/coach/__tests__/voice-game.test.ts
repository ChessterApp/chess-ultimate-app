import { describe, it, expect } from 'vitest';
import {
  VOICE_GAME_GUIDANCE,
  VOICE_GAME_TOOLS,
  gameMoveResult,
  gameNote,
  gameStartResult,
  nearestStrength,
  spokenMoveToUci,
} from '../voice-game';
import type { GameStateView } from '../boards-api';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
// 1.e4 d5 — Alexander's game (10.10): White to take on d5
const SCANDI = 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2';

function view(over: Partial<GameStateView> = {}): GameStateView {
  return {
    board_id: 'b1', student_color: 'white', engine_elo: 1200, comment_mode: 'quiet', status: 'playing',
    result: null, termination: null, winner: null, fen: START, pgn: '', ply: 0, moves: [],
    student_to_move: true, in_check: false, student: null, engine: null, comment_wanted: false,
    ...over,
  } as GameStateView;
}

describe('voice game: the student\'s move as the model writes it', () => {
  it.each([
    ['exd5', 'e4d5', 'exd5'],
    ['е:д5', 'e4d5', 'exd5'],  // Russian notation
    ['e4d5', 'e4d5', 'exd5'],
    ['e4-d5', 'e4d5', 'exd5'],
    ['Nf3', 'g1f3', 'Nf3'],
    ['Кf3', 'g1f3', 'Nf3'],
    ['Nf3+', 'g1f3', 'Nf3'],
  ])('%s → %s', (move, uci, san) => {
    expect(spokenMoveToUci(SCANDI, move)).toEqual({ uci, san });
  });

  it('an illegal move comes back with the legal ones, nothing played', () => {
    const r = spokenMoveToUci(SCANDI, 'Qd4');
    expect('error' in r && r.error).toMatch(/not a legal move/);
    expect('legal' in r && r.legal).toContain('exd5');
    expect('error' in spokenMoveToUci(START, '')).toBe(true);
  });

  it('castling with zeros and promotion', () => {
    const castle = 'r3k2r/8/8/8/8/8/8/R3K2R w KQkq - 0 1';
    expect(spokenMoveToUci(castle, '0-0')).toEqual({ uci: 'e1g1', san: 'O-O' });
    expect(spokenMoveToUci('8/P6k/8/8/8/8/8/K7 w - - 0 1', 'a8=Q')).toEqual({ uci: 'a7a8q', san: 'a8=Q' });
  });
});

describe('voice game: what the model hears', () => {
  it('the start says the engine\'s first move when the student plays Black', () => {
    const r = gameStartResult(view({ student_color: 'black', student_to_move: true, engine: { san: 'e4', uci: 'e2e4' } }));
    expect(r).toMatchObject({ ok: true, student_color: 'black', engine_first_move: 'e4' });
    expect(String(r.note)).toContain('e4');
  });

  it('a move result carries the engine reply, and the better move only after a mistake', () => {
    const ok = gameMoveResult(view({ student: { san: 'exd5', uci: 'e4d5', verdict: 'ok', cp_loss: 0, eval_after: 0.3, best: 'exd5' }, engine: { san: 'Qxd5', uci: 'd8d5' } }));
    expect(ok).toMatchObject({ ok: true, student_move: 'exd5', engine_reply: 'Qxd5' });
    expect(ok).not.toHaveProperty('better_was');
    const bad = gameMoveResult(view({ student: { san: 'Qh5', uci: 'd1h5', verdict: 'blunder', cp_loss: 400, eval_after: -3, best: 'exd5' }, engine: { san: 'Nf6', uci: 'g8f6' } }));
    expect(bad).toMatchObject({ verdict: 'blunder', better_was: 'exd5' });
  });

  it('the game over is said', () => {
    const r = gameMoveResult(view({ status: 'finished', result: '1-0', termination: 'checkmate', winner: 'student', student: { san: 'Qxf7#', uci: 'h5f7', verdict: 'ok', cp_loss: 0, eval_after: 100, best: null } }));
    expect(r).toMatchObject({ game_over: true, result: '1-0', winner: 'student' });
  });

  it('the [Game] line names both moves and keeps board_control off the position', () => {
    const note = gameNote(view({ fen: SCANDI, student: { san: 'e4', uci: 'e2e4', verdict: 'ok', cp_loss: 0, eval_after: 0.3, best: null }, engine: { san: 'd5', uci: 'd7d5' } }));
    expect(note).toMatch(/^\[Game\]/);
    expect(note).toContain('the student played e4');
    expect(note).toContain('the engine answered d5');
    expect(note).toContain(SCANDI);
    expect(note).toContain('never change the position with board_control');
  });

  it('strengths snap to the ones the site offers', () => {
    expect(nearestStrength(1300)).toBe(1200);
    expect(nearestStrength(undefined)).toBe(1200);
    expect(nearestStrength(3000)).toBe(2500);
  });

  it('the declarations and the prompt name the two tools', () => {
    expect(VOICE_GAME_TOOLS.map((t) => t.name)).toEqual(['start_game', 'make_game_move']);
    expect(VOICE_GAME_GUIDANCE).toContain('start_game');
    expect(VOICE_GAME_GUIDANCE).toContain('make_game_move');
    expect(VOICE_GAME_GUIDANCE).toContain('never write a FEN by hand');
  });
});
