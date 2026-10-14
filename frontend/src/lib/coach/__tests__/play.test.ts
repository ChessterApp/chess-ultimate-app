import { describe, it, expect } from 'vitest';
import { GAME_STRENGTHS, eloLevel, moveVerdict, coachRemark, nearestStrengthIndex, rematchOptions } from '../play';
import type { GameStateView } from '../boards-api';

describe('eloLevel', () => {
  it('names every offered strength', () => {
    expect(GAME_STRENGTHS.map(eloLevel)).toEqual([
      'novice', 'novice', 'amateur', 'amateur', 'club', 'expert', 'expert', 'master', 'master',
    ]);
  });

  it('snaps a rating to the nearest offered strength', () => {
    expect(GAME_STRENGTHS[nearestStrengthIndex(1234)]).toBe(1200);
    expect(GAME_STRENGTHS[nearestStrengthIndex(100)]).toBe(600);
    expect(GAME_STRENGTHS[nearestStrengthIndex(3000)]).toBe(2500);
  });
});

const student = (o: Partial<NonNullable<GameStateView['student']>>) => ({
  san: 'Nf3', uci: 'g1f3', verdict: 'ok' as const, cp_loss: 0, eval_after: 20, best: null, ...o,
});

describe('moveVerdict', () => {
  it('badges a mistake on the destination square', () => {
    expect(moveVerdict(student({ san: 'h4', uci: 'h2h4', verdict: 'blunder', best: 'e4' }))).toEqual({
      kind: 'blunder', square: 'h4', san: 'h4', best: 'e4',
    });
    expect(moveVerdict(student({ verdict: 'inaccuracy' }))?.kind).toBe('inaccuracy');
  });

  it('marks the engine’s best move, says nothing about an ordinary one', () => {
    expect(moveVerdict(student({ best: 'Nf3' }))?.kind).toBe('best');
    expect(moveVerdict(student({ best: 'e4' }))).toBeNull();
    expect(moveVerdict(null)).toBeNull();
  });

  it('uses the destination of a promotion', () => {
    expect(moveVerdict(student({ uci: 'a7a8q', verdict: 'mistake' }))?.square).toBe('a8');
  });
});

describe('rematchOptions', () => {
  const game = { student_color: 'black', engine_elo: 1800, comment_mode: 'every' } as GameStateView;
  it('replays the last start settings (a random colour stays random)', () => {
    const last = { color: 'random', elo: 1500, comment_mode: 'quiet' } as const;
    expect(rematchOptions(game, last)).toEqual(last);
  });
  it('falls back to the finished game', () => {
    expect(rematchOptions(game, null)).toEqual({ color: 'black', elo: 1800, comment_mode: 'every' });
  });
});

describe('coachRemark', () => {
  it('keeps every sentence, without markdown', () => {
    expect(coachRemark('**Рановато** для Ng5. Отвечу d5!\n\nСмотри [сюда](https://x.y).')).toBe(
      'Рановато для Ng5. Отвечу d5! Смотри сюда.'
    );
  });

  it('caps a long remark at a word boundary', () => {
    const out = coachRemark('слово '.repeat(200));
    expect(out.length).toBeLessThanOrEqual(600);
    expect(out.endsWith('слово…')).toBe(true);
  });

  it('a 300-char remark is kept whole', () => {
    const text = 'Ты верно развиваешь коня. '.repeat(11).trim();
    expect(text.length).toBeGreaterThan(280);
    expect(coachRemark(text)).toBe(text);
  });

  it('nothing but markdown is empty', () => {
    expect(coachRemark('```\ncode\n```')).toBe('');
  });
});
