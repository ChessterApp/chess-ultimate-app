import { describe, it, expect } from 'vitest';
import {
  extendsSentText, fillerFor, groupChunks, localeOf, looksLikeMove, movePhrase, newWords, rotationDue, speakable, spokenMove, splitLong, takeSentences, ttsRetryDelay, utteranceReady,
  SILENCE_MS, STT_STABLE_MS, STT_STABLE_SLOW_MS, STT_ROTATE_MS, STT_ROTATE_HARD_MS, STT_QUIET_MS, TTS_WAIT_MAX_MS,
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

describe('the transcription connection over a long session (25.10)', () => {
  const opened = 100_000;

  it('is swapped in a quiet moment once it is seven minutes old, never while the student talks or words wait', () => {
    const t = opened + STT_ROTATE_MS;
    expect(rotationDue(t - 1000, opened, null, false)).toBeNull();                       // too young
    expect(rotationDue(t, opened, null, false)).toBe('soft');                             // quiet, nothing unsent
    expect(rotationDue(t, opened, t - STT_QUIET_MS + 100, false)).toBeNull();             // still talking
    expect(rotationDue(t, opened, t - STT_QUIET_MS - 100, false)).toBe('soft');
    expect(rotationDue(t, opened, null, true)).toBeNull();                                // words not yet sent
  });

  it('is swapped as soon as the server says goAway, in the next quiet moment', () => {
    expect(rotationDue(opened + 60_000, opened, null, false, true)).toBe('soft');
    expect(rotationDue(opened + 60_000, opened, opened + 59_500, false, true)).toBeNull();
  });

  it('is swapped regardless once it is nine minutes old', () => {
    const t = opened + STT_ROTATE_HARD_MS;
    expect(rotationDue(t, opened, t - 100, true)).toBe('hard');
  });
});

describe('a TTS call that failed (25.10)', () => {
  it('waits out the quota, longer each time, and never past the cap', () => {
    expect(ttsRetryDelay(429, 0, 0)).toBe(1000);
    expect(ttsRetryDelay(429, 1, 1000)).toBe(2000);
    expect(ttsRetryDelay(429, 3, 7000)).toBe(8000);
    expect(ttsRetryDelay(429, 6, 31_000)).toBe(8000);
    expect(ttsRetryDelay(429, 7, TTS_WAIT_MAX_MS)).toBeNull();
  });

  it('gives a blip a second, three times, and gives up on anything else', () => {
    expect(ttsRetryDelay(502, 0, 0)).toBe(1000);
    expect(ttsRetryDelay(503, 2, 2000)).toBe(1000);
    expect(ttsRetryDelay(502, 3, 3000)).toBeNull();
    expect(ttsRetryDelay(400, 0, 0)).toBeNull();
    expect(ttsRetryDelay(401, 0, 0)).toBeNull();
  });
});

describe('a move said by the system before the model speaks (25.10)', () => {
  it('reads SAN as a listener follows it', () => {
    expect(spokenMove('e4')).toBe('е четыре');
    expect(spokenMove('Nf3')).toBe('конь эф три');
    expect(spokenMove('exd5')).toBe('е бьёт дэ пять');
    expect(spokenMove('Bxc6+')).toBe('слон бьёт цэ шесть, шах');
    expect(spokenMove('Qh7#')).toBe('ферзь аш семь, мат');
    expect(spokenMove('O-O')).toBe('короткая рокировка');
    expect(spokenMove('O-O-O+')).toBe('длинная рокировка, шах');
    expect(spokenMove('e8=Q')).toBe('е восемь превращается в ферзь');
    expect(spokenMove('Nf3', 'en')).toBe('knight f3');
    expect(spokenMove('exd5', 'en')).toBe('e takes d5');
    expect(spokenMove('Nf3', 'kk')).toBe('ат эф үш');
    expect(spokenMove('weird')).toBe('weird');
  });

  it('phrases the move and the reply, or nothing when no move of the student is in the view', () => {
    expect(movePhrase({ student: { san: 'e4' }, engine: { san: 'e5' }, status: 'playing' })).toBe('е четыре. Отвечаю е пять.');
    expect(movePhrase({ student: { san: 'Qxf7#' }, engine: null, status: 'finished' })).toBe('ферзь бьёт эф семь, мат. Партия окончена.');
    expect(movePhrase({ student: { san: 'e4' }, engine: { san: 'c5' }, status: 'playing' }, 'en')).toBe('e4. I reply c5.');
    expect(movePhrase({ student: null, engine: { san: 'e4' }, status: 'playing' })).toBeNull();
  });

  it('knows a move from a question, so the filler is skipped only for moves', () => {
    for (const t of ['е четыре', 'конь эф три', 'Ну, слон цэ четыре.', 'e4', 'я пойду d4', 'короткая рокировка', 'Коня в три.']) expect(looksLikeMove(t), t).toBe(true);
    for (const t of ['что думаешь про позицию', 'дай задачу на связку', 'а если конь эф три, это хорошо или плохо?', 'ладно']) expect(looksLikeMove(t), t).toBe(false);
  });
});

describe('the final transcript that extends an interim one already sent (25.10)', () => {
  it('is the same utterance when it only adds words or changes punctuation', () => {
    expect(extendsSentText('Давай сыграем, я белыми.', 'Давай сыграем.')).toBe(true);
    expect(extendsSentText('Конь эф три!', 'конь эф')).toBe(true);
    expect(extendsSentText('Давай сыграем.', 'Давай сыграем.')).toBe(false);   // nothing new: no second send
    expect(extendsSentText('Что думаешь про позицию?', 'Давай сыграем.')).toBe(false);
    expect(extendsSentText('', 'Давай')).toBe(false);
  });
});
