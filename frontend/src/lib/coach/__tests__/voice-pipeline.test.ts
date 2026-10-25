import { describe, it, expect } from 'vitest';
import {
  fillerFor, groupChunks, localeOf, newWords, speakable, splitLong, takeSentences, utteranceReady,
  SILENCE_MS, STT_STABLE_MS, STT_STABLE_SLOW_MS,
} from '../voice-pipeline';

describe('voice pipeline helpers', () => {
  it('strips markdown, links and board markup before speech', () => {
    expect(speakable('**Rc3#** — мат!\n\n- Ладья с c8 идёт на c3.\n[[arrows: c8c3 green]] См. урок [Связка](https://chesster.io/learn/x).'))
      .toBe('Rc3# — мат! Ладья с c8 идёт на c3. См. урок Связка.');
    expect(speakable('### План\n1. Рокировка\n2. `d4`')).toBe('План Рокировка d4');
  });

  it('takes whole sentences and keeps the tail; a move number is not a boundary', () => {
    expect(takeSentences('Сейчас посмотрю. Под ударом слон c4! А ещё')).toEqual({
      sentences: ['Сейчас посмотрю.', 'Под ударом слон c4!'], rest: ' А ещё',
    });
    expect(takeSentences('Лучше 1.e4 e5 2.Nf3 — так играют. Потом')).toEqual({
      sentences: ['Лучше 1.e4 e5 2.Nf3 — так играют.'], rest: ' Потом',
    });
    expect(takeSentences('Что скажешь?» Ну', false).sentences).toEqual(['Что скажешь?»']);
    expect(takeSentences(' А ещё конь', true)).toEqual({ sentences: ['А ещё конь'], rest: '' });
    expect(takeSentences('', true)).toEqual({ sentences: [], rest: '' });
  });

  it('closes an utterance after silence and a stable transcript', () => {
    const now = 10_000;
    expect(utteranceReady('', now, now - 5000, now - 5000)).toBe(false);
    expect(utteranceReady('Какой здесь лучший ход?', now, now - STT_STABLE_MS, now - SILENCE_MS)).toBe(true);
    expect(utteranceReady('Какой здесь лучший ход?', now, now - STT_STABLE_MS + 50, now - SILENCE_MS)).toBe(false);
    expect(utteranceReady('Какой здесь лучший ход?', now, now - STT_STABLE_MS, now - SILENCE_MS + 100)).toBe(false);  // still speaking
    expect(utteranceReady('Какой здесь лучший ход', now, now - STT_STABLE_MS, now - SILENCE_MS)).toBe(false);          // no mark: wait longer
    expect(utteranceReady('Какой здесь лучший ход', now, now - STT_STABLE_SLOW_MS, now - SILENCE_MS)).toBe(true);
    expect(utteranceReady('e4', now, now - STT_STABLE_SLOW_MS, null)).toBe(true);
  });

  it('takes only the new words of a running transcript', () => {
    expect(newWords('Привет! Какой здесь лучший ход?', 'Привет!')).toBe('Какой здесь лучший ход?');
    expect(newWords('Какой здесь лучший ход?', '')).toBe('Какой здесь лучший ход?');
    expect(newWords('Новая фраза.', 'Старая фраза.')).toBe('Новая фраза.');
  });

  it('tells the language of the words and picks a filler', () => {
    expect(localeOf('Какой здесь лучший ход?')).toBe('ru');
    expect(localeOf('Бұл позицияда не істеу керек?')).toBe('kk');
    expect(localeOf('What should I play here?')).toBe('en');
    expect(localeOf('e4')).toBe('ru');           // a bare move in Latin letters: the interface language
    expect(localeOf('', 'kk')).toBe('kk');
    expect(fillerFor('ru', 0)).toBe('/voice/fillers/ru-1.pcm');
    expect(fillerFor('en', 0.99)).toBe('/voice/fillers/en-2.pcm');
  });

  it('groups short sentences into one TTS call and keeps a short tail for the next', () => {
    const long = 'Под ударом твой слон на c4, его атакует конь с a5, а защитников у слона нет.';
    expect(groupChunks(['Отлично, играем!', 'Ты белыми, ход твой.'])).toEqual({ chunks: [], waiting: ['Отлично, играем!', 'Ты белыми, ход твой.'] });
    expect(groupChunks(['Отлично, играем!', 'Ты белыми, ход твой.', long])).toEqual({ chunks: [`Отлично, играем! Ты белыми, ход твой. ${long}`], waiting: [] });
    expect(groupChunks(['Жду ход.'], true)).toEqual({ chunks: ['Жду ход.'], waiting: [] });
    expect(groupChunks([long, 'Жду.'], false)).toEqual({ chunks: [long], waiting: ['Жду.'] });
  });

  it('reads a long chunk in parts split at commas, never mid-word', () => {
    const long = 'Беру задачу на связку, сначала посмотрю позицию на доске: вот твоя программа, ступень один, урок «Связка», и в нём как раз показано, как устроена связка и как её использовать в партии.';
    const parts = splitLong(long, 80);
    expect(parts.length).toBeGreaterThan(1);
    expect(parts.every((p) => p.length <= 80)).toBe(true);
    expect(parts.join(' ').replace(/\s+/g, ' ')).toBe(long.replace(/[,:]/g, (m) => m).replace(/\s+/g, ' '));
    expect(splitLong('Короткая фраза.')).toEqual(['Короткая фраза.']);
  });
});
