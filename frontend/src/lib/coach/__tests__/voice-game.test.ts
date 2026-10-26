import { describe, it, expect } from 'vitest';
import { famousNote, gameActionNote, gameFromActions, gameMoveNote, gameNote, gameStartNote, mayAskForAGame, mayCommandTheGame, mentionsAGame } from '../voice-game';
import type { GameStateView } from '../boards-api';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
// 1.e4 d5 — Alexander's game (10.10)
const SCANDI = 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2';

function view(over: Partial<GameStateView> = {}): GameStateView {
  return {
    board_id: 'b1', student_color: 'white', engine_elo: 1200, comment_mode: 'quiet', status: 'playing',
    result: null, termination: null, winner: null, fen: START, pgn: '', ply: 0, moves: [],
    student_to_move: true, in_check: false, student: null, engine: null, comment_wanted: false,
    ...over,
  } as GameStateView;
}

describe('voice: the game the coach plays (Hermes start_game / make_game_move)', () => {
  it('the game state comes out of the board actions', () => {
    const g = view({ fen: SCANDI });
    expect(gameFromActions([{ type: 'draw_arrows', arrows: [] }, { type: 'game', game: g }])).toBe(g);
    expect(gameFromActions([{ type: 'set_fen', fen: START }])).toBeNull();
    expect(gameFromActions(undefined)).toBeNull();
  });

  it('the [Game] line names both moves and keeps board_control off the position', () => {
    const note = gameNote(view({ fen: SCANDI, student: { san: 'e4', uci: 'e2e4', verdict: 'ok', cp_loss: 0, eval_after: 0.3, best: null }, engine: { san: 'd5', uci: 'd7d5' } }));
    expect(note).toMatch(/^\[Game\]/);
    expect(note).toContain('the student played e4');
    expect(note).toContain('the engine answered d5');
    expect(note).toContain(SCANDI);
    expect(note).toContain('make_game_move');
  });

  it('the end of the game is said', () => {
    const note = gameNote(view({ status: 'finished', result: '0-1', termination: 'checkmate' }));
    expect(note).toContain('The game is over: 0-1 checkmate');
  });
});

describe('voice: a famous game by name (Hermes famous_game)', () => {
  it('only words that may name a game are looked up', () => {
    expect(mentionsAGame('Покажи оперную партию Морфи')).toBe(true);
    expect(mentionsAGame('show me the immortal game')).toBe(true);
    expect(mentionsAGame('как ходит конь')).toBe(false);
  });

  it('the note carries the verified facts, or nothing', () => {
    expect(famousNote({ found: true, facts: '## The famous game … ALREADY on the board' })).toMatch(/^\[Game record\] ## The famous game/);
    expect(famousNote({ found: false })).toBeNull();
    expect(famousNote(null)).toBeNull();
  });
});

describe('voice: the game asked for or the move said, done by Hermes for the words', () => {
  it('only words that may ask for a game go to start_game', () => {
    expect(mayAskForAGame('Спорим, я тебя обыграю? Давай сыграем')).toBe(true);
    expect(mayAskForAGame("let's play")).toBe(true);
    expect(mayAskForAGame('почему здесь связка')).toBe(false);
  });

  it('the notes say what the system did, and nothing for a refusal', () => {
    expect(gameStartNote({ ok: true, student_color: 'black', note: 'The engine opened with e4.' })).toContain('the student plays black');
    expect(gameMoveNote({ ok: true, student_move: 'e4', verdict: 'ok', engine_reply: 'd5' })).toMatch(/e4 was played .* the engine answered d5/);
    expect(gameMoveNote({ ok: true, student_move: 'Qh5', verdict: 'blunder', engine_reply: 'Nf6' })).toContain('Qh5 (blunder)');
    expect(gameStartNote(null)).toBeNull();
    expect(gameMoveNote({ ok: false })).toBeNull();
  });
});

describe('voice: the game\'s buttons said in words (Hermes game_action)', () => {
  it('only words that may ask the game for something go to game_action', () => {
    for (const t of ['Сдаюсь', 'Ой, верни ход назад', 'давай заново', 'Предлагаю ничью', 'I resign', 'take back', 'new game']) {
      expect(mayCommandTheGame(t)).toBe(true);
    }
    expect(mayCommandTheGame('конь f3')).toBe(false);
    expect(mayCommandTheGame('почему здесь связка')).toBe(false);
  });

  it('the note says what the system did, and nothing without an action', () => {
    expect(gameActionNote({ action: 'resign', done: true, note: 'Result 0-1.' })).toMatch(/^\[Game\] The student resigned/);
    expect(gameActionNote({ action: 'draw', done: false, note: 'Declined because it is too early.' })).toContain('offered a draw');
    expect(gameActionNote(null)).toBeNull();
    // 26.10: the audio-mode controls the site does for the student's words
    expect(gameActionNote({ action: 'view', done: true, note: 'Shown: after move 1.' })).toMatch(/EARLIER position.*goes on from its live position/);
    expect(gameActionNote({ action: 'mistake', done: true, note: 'Undone.' })).toContain('ask which move they want');
    expect(gameActionNote({ action: 'continue_here', done: true, note: '' })).toContain('cut there');
    expect(gameActionNote({})).toBeNull();
  });
});
