import { describe, expect, it } from 'vitest';

import { CONCEPT_QUESTION_RE, OPENING_HINT_RE, openingNote, topicNote } from '../useGeminiLive';

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
