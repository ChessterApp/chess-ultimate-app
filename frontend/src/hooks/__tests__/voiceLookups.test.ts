import { describe, expect, it } from 'vitest';

import { CONCEPT_QUESTION_RE, IDEA_MOVE_RE, OPENING_HINT_RE, openingNote, topicNote } from '../useGeminiLive';

describe('voice lookups: what the site asks Hermes about on its own', () => {
  it('an opening named in the words is looked up (slang included)', () => {
    for (const text of [
      'что такое жареная печень',
      'как играть против детского мата',
      'хочу перевести игру в лондонскую систему',
      'как из этой позиции перейти в защиту двух коней',
      'what is the fried liver attack',
    ]) {
      expect(OPENING_HINT_RE.test(text), text).toBe(true);
    }
  });

  it('a concept question is still a concept question', () => {
    expect(CONCEPT_QUESTION_RE.test('объясни, что такое связка')).toBe(true);
    expect(OPENING_HINT_RE.test('объясни, что такое связка')).toBe(false);
  });

  it('the opening note carries the book block; nothing found → nothing sent', () => {
    expect(openingNote({ found: false })).toBeNull();
    const note = openingNote({ found: true, name: 'Italian Game: Two Knights Defense, Fried Liver Attack',
      note: '## The opening the student asked about\nC57 …\nBook line: 1. e4 e5' });
    expect(note).toMatch(/^\[Opening\] ## The opening the student asked about C57 … Book line: 1\. e4 e5$/);
  });

  it('the topic note still describes the example on the board', () => {
    expect(topicNote({ title: 'Связка', example: { fen: '8/8/8/8/8/8/8/8 w - - 0 1', title: 'пример' } })).toContain('[Topic]');
    expect(topicNote({ title: 'Связка' })).toBeNull();
    // The site's own lesson: the task is a puzzle, the solution stays hidden, the lesson is where to go.
    const lesson = topicNote({
      title: 'Связка',
      example: {
        source: 'site_lesson', kind: 'task', title: 'Связка', course: 'Основы шахмат', tasks: 12,
        fen: '8/8/7p/5K1k/7r/7R/6P1/8 w - - 0 1', side_to_move: 'White', solution: ['g4#'],
        url: 'https://chesster.io/learn/chess-basics/pin',
      },
    })!;
    expect(lesson).toContain("the first task of the site's lesson «Связка» (course «Основы шахмат»), which has 12 tasks");
    expect(lesson).toContain('Its solution is g4# — do not reveal it');
    expect(lesson).toContain('send them to the whole lesson');
    expect(lesson).toContain('https://chesster.io/learn/chess-basics/pin');
    expect(lesson).not.toContain('knowledge-base example');
  });
});

import { SPEECH_CHECKABLE_RE, SPEECH_SENTENCE_END_RE, correctionNote } from '../useGeminiLive';

describe('voice check: what the coach said, read back when wrong', () => {
  it('only sentences with chess content are checked', () => {
    expect(SPEECH_CHECKABLE_RE.test('Конь с f3 прыгает на d5.')).toBe(true);
    expect(SPEECH_CHECKABLE_RE.test('Отличный вопрос, давай разберём.')).toBe(false);
  });

  it('sentences end at . ! ? followed by a space', () => {
    const m = SPEECH_SENTENCE_END_RE.exec('Смотри на f7. Конь');
    expect(m && m.index).toBe(12);
  });

  it('the correction note names the sentence and why it is wrong; nothing wrong → no note', () => {
    expect(correctionNote([])).toBeNull();
    const note = correctionNote([{ text: 'Конь с f3 прыгает на d5.', issues: ['a knight cannot move from f3 to d5'] }]);
    expect(note).toContain('[Check]');
    expect(note).toContain('«Конь с f3 прыгает на d5.» — a knight cannot move from f3 to d5');
    expect(note).toMatch(/Correct yourself now/);
  });
});

import { PUZZLE_REQUEST_RE, PUZZLE_THEME_RE, REVIEW_REQUEST_RE, REVIEW_SIDE_RE, puzzleNote, reviewNote } from '../useGeminiLive';

describe('voice shortcuts: puzzle and review fetched by the site', () => {
  it('a puzzle request is recognised, with its theme', () => {
    for (const text of ['дай задачу на вилку', 'давай решим задачу', 'give me a puzzle on pins', 'хочу ещё одну задачу']) {
      expect(PUZZLE_REQUEST_RE.test(text), text).toBe(true);
    }
    expect(PUZZLE_THEME_RE.exec('дай задачу на вилку')?.[1]).toBe('вилку');
    expect(PUZZLE_THEME_RE.exec('давай решим задачу')).toBeNull();
    expect(PUZZLE_REQUEST_RE.test('какая тут задача у белых?')).toBe(false);
  });

  it('the puzzle note names the side, keeps the solution private', () => {
    const note = puzzleNote({ theme: 'fork', puzzles: [{ fen: '8/8/8/8/8/8/8/8 b - - 0 1', solution: ['Nc2+', 'Kd1'], rating: 1200 }] });
    expect(note).toContain('[Puzzle]');
    expect(note).toContain('Black to move');
    expect(note).toContain('Solution (private');
    expect(puzzleNote({ puzzles: [] })).toBeNull();
  });

  it('a review request is recognised, with the side', () => {
    for (const text of ['разбери мою партию', 'где я ошибся?', 'review my game', 'проанализируй эту партию, я играл чёрными']) {
      expect(REVIEW_REQUEST_RE.test(text), text).toBe(true);
    }
    expect(REVIEW_REQUEST_RE.test('что мне здесь играть?')).toBe(false);
    const m = REVIEW_SIDE_RE.exec('я играл чёрными');
    expect(m && !!m[1]).toBe(true);
    expect(reviewNote({ note: '## Critical moments\n- 16...Bh5' })).toBe('[Review] ## Critical moments\n- 16...Bh5');
    expect(reviewNote({})).toBeNull();
  });
});


describe('IDEA_MOVE_RE — a move in the student\'s words', () => {
  it('matches notation and words for a move', () => {
    for (const text of [
      'а если Rg1?', 'а что если поставить ладью на g1', 'ладьёй взять на h4', 'взять ферзя конём',
      'коня с f3 на d5', 'what if I put the rook on g1', 'take the queen with the knight', 'knight to d5',
      'а если Лg1', 'может Nxe5?',
      // 2026-10-06: castling and a bare pawn move reach the engine too
      'можно мне рокироваться?', 'а если 0-0?', 'can I castle kingside?', 'а если b3?', 'если пешка пойдёт b3',
      'what about b3?',
    ]) {
      expect(IDEA_MOVE_RE.test(text), text).toBe(true);
    }
  });
  it('leaves other talk alone', () => {
    for (const text of ['что мне делать?', 'что такое связка', 'привет', 'кто впереди по материалу', 'what should I play here',
      'счёт 1-0 в мою пользу', 'на поле e4 стоит пешка?']) {
      expect(IDEA_MOVE_RE.test(text), text).toBe(false);
    }
  });
});
