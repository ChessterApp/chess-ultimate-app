import { describe, expect, it } from 'vitest';
import { boardInWords, leakNote, noteLeak, shownText, stripNotes, unshownNote } from '../voice-notes';
import { speakable } from '../voice-pipeline';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

// Alexander's phone, 10.11: «Секунду, сейчас всё исправлю. [Board] …» — and a position record read aloud.
describe('a system record in the coach\'s words', () => {
  it.each([
    ['Секунду, сейчас всё исправлю. [Board] Current position (FEN): 4r1k1/8/8/8/8/8/8/4K3 w - - 0 1', 'tag', 30],
    ['[Engine] Best: e4', 'tag', 0],
    ['Смотри. [Диаграмма: 6k1/5pp1/8/8/8/8/8/6K1 w - - 0 1]', 'tag', 8],
    ['Вот. [Картинка учебника: позиции нет]', 'tag', 5],
    ['Міне: [Тақта] e1', 'tag', 6],
    ['Ставлю 4r1k1/8/8/8/8/8/8/4K3 w - - 0 1 на доску', 'fen', 7],
    ['Сейчас. board_control(action_type="set_fen")', 'tool', 8],
    ['Вызываю get_topic', 'tool', 8],
    ['Ок. {"fen": "8/8"}', 'tool', 4],
    ['Current position (FEN): start', 'echo', 0],
  ])('%s → %s', (text, kind, index) => {
    expect(noteLeak(text)).toEqual({ kind, index });
  });

  it.each([
    'Конь на f3 защищает пешку e5, а слон идёт на c4.',
    'Сыграй 1. e4 e5 2. Кf3 — и ладья a1 пока стоит.',
    'Белые выиграли 1-0, а до этого было 1/2.',
    'Ход [e4] здесь лучший.',
    'The knight on f3 attacks e5; play d4 next.',
    'Ат f3-ке барады, содан кейін піл c4-ке.',
    'Оценка примерно равная (плюс-минус).',
  ])('plain chess talk is not one: %s', (text) => {
    expect(noteLeak(text)).toBeNull();
    expect(shownText(text)).toBe(text);
  });

  it('the chat shows the words without the record', () => {
    expect(shownText('Секунду, сейчас всё исправлю. [Board] Current position (FEN): 4r1k1/8/8/8/8/8/8/4K3 w - - 0 1')).toBe('Секунду, сейчас всё исправлю.');
    expect(shownText('[Idea] Ход b3 теряет слона.')).toBe('Ход b3 теряет слона.');   // production, 2026-10-07
    expect(shownText('Ставлю rnbqkbnr/pppppppp/8/8/4P3/8 и дальше')).toBe('Ставлю и дальше');
  });

  it('a tag still arriving is not shown either', () => {
    expect(shownText('Сейчас поставлю. [Bo')).toBe('Сейчас поставлю.');
    expect(shownText('Сейчас поставлю. [')).toBe('Сейчас поставлю.');
  });
});

describe('the pipeline reads no record aloud', () => {
  it('takes the records out and keeps the sentence', () => {
    expect(speakable('Смотри [Board] на позицию.')).toBe('Смотри на позицию.');
    expect(speakable('Позиция: rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1. Белые начинают.')).toBe('Позиция:. Белые начинают.');
    expect(speakable('Я вызвал board_control(set_fen) и готово.')).toBe('Я вызвал и готово.');
    expect(speakable('Вот [[arrows: e2e4 green]] ход e4 и [урок](https://chesster.io/learn/x).')).toBe('Вот ход e4 и урок.');
  });

  it('a sentence that was nothing but a record is not read', () => {
    expect(speakable('[Board] Current position (FEN): 4r1k1/8/8/8/8/8/8/4K3 w - - 0 1.')).toBe('');
    expect(speakable('[Диаграмма: 6k1/5pp1/8/8/8/8/8/6K1 w - - 0 1]')).toBe('');
  });

  it('stripNotes keeps everything else', () => {
    expect(stripNotes('Конь f3, слон c4 — 1. e4 e5.')).toBe('Конь f3, слон c4 — 1. e4 e5.');
  });
});

describe('what the coach is told', () => {
  it('names the board in words', () => {
    expect(boardInWords(START)).toBe('the starting position');
    expect(boardInWords('8/8/8/8/8/8/8/8 w - - 0 1')).toBe('an empty board');
    expect(boardInWords('6k1/8/8/8/8/8/8/6K1 w - - 0 1')).toBe('the position 6k1/8/8/8/8/8/8/6K1 w - - 0 1');
    expect(boardInWords(undefined)).toBe('the same position as before');
  });

  it('a record read aloud: nothing changed, the board changes through a tool', () => {
    const note = leakNote(START);
    expect(note).toMatch(/^\[Voice\] /);
    expect(note).toContain('the board still shows the starting position');
    expect(note).toContain('get_topic or get_lesson');
    expect(noteLeak(note.slice('[Voice] '.length).replace(/get_topic|get_lesson|board_control|load_pgn/g, 'x'))).toBeNull();
  });

  it('a position that is not on the board', () => {
    const note = unshownNote(' Видишь, белого короля атакует чёрная ладья? ', START);
    expect(note).toContain('«Видишь, белого короля атакует чёрная ладья?»');
    expect(note).toContain('it shows the starting position');
    expect(note).toContain('call get_topic');
  });
});
