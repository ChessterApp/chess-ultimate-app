import { describe, expect, it } from 'vitest';
import { LESSON_XP, lessonXp } from '../lessonXp';

describe('lessonXp — XP by lesson type and course level', () => {
  it('has the agreed table (level → theory / exercise)', () => {
    expect(Object.entries(LESSON_XP).map(([lvl, r]) => [lvl, r.theory, r.exercise])).toEqual([
      ['beginner', 10, 15],
      ['intermediate', 15, 20],
      ['advanced', 20, 25],
      ['master', 25, 30],
      ['expert', 30, 35],
      ['legendary', 35, 40],
      ['grandmaster', 40, 50],
    ]);
  });

  it('looks up by type and level', () => {
    expect(lessonXp('theory', 'beginner')).toBe(10);
    expect(lessonXp('exercise', 'beginner')).toBe(15);
    expect(lessonXp('exercise', 'grandmaster')).toBe(50);
    expect(lessonXp('theory', 'legendary')).toBe(35);
  });

  it('falls back: unknown level → beginner, unknown type → theory', () => {
    expect(lessonXp('exercise', 'nonsense')).toBe(15);
    expect(lessonXp('exercise', null)).toBe(15);
    expect(lessonXp('exercise', 'toString')).toBe(15);
    expect(lessonXp('quiz', 'master')).toBe(25);
    expect(lessonXp(undefined, undefined)).toBe(10);
  });
});
