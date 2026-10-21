import { describe, it, expect } from 'vitest';
import { marksFor, parseCoachMarkup } from '../review-markup';

describe('parseCoachMarkup', () => {
  it('cuts the marks of the production leak (2026-10-21) and keeps their arrows', () => {
    const raw =
      '[[arrows: c6d4 green, d4e2 red]]. Из центра конь разом бьёт по b3, давит на d2 и e2. ' +
      'Другой ход, вроде взятия на d5, оставлял бы белым куда больше шансов [[arrows: d8d5 blue]],';
    const { text, arrows } = parseCoachMarkup(raw);
    expect(text).toBe(
      'Из центра конь разом бьёт по b3, давит на d2 и e2. ' +
        'Другой ход, вроде взятия на d5, оставлял бы белым куда больше шансов,',
    );
    expect(arrows).toEqual([
      { from: 'c6', to: 'd4', brush: 'green' },
      { from: 'd4', to: 'e2', brush: 'red' },
      { from: 'd8', to: 'd5', brush: 'blue' },
    ]);
  });

  it('turns squares marks into highlights', () => {
    const { text, squares } = parseCoachMarkup('Weak squares [[squares: d4 e5]] here.');
    expect(text).toBe('Weak squares here.');
    expect(squares).toEqual(['d4', 'e5']);
  });

  it('defaults an arrow without colour to green and reads bare short marks', () => {
    expect(parseCoachMarkup('Play [[g1f3]].').arrows).toEqual([{ from: 'g1', to: 'f3', brush: 'green' }]);
    expect(parseCoachMarkup('Nice [[red]] move.').text).toBe('Nice move.');
  });

  it('hides an unfinished trailing mark while streaming', () => {
    expect(parseCoachMarkup('The knight jumps [[arrows: c6').text).toBe('The knight jumps');
  });

  it('leaves text without marks (and foreign [[…]]) untouched', () => {
    expect(parseCoachMarkup('Plain  text.').text).toBe('Plain  text.');
    const long = '[[this is some long bracketed note that is not a board mark at all]]';
    expect(parseCoachMarkup(long).text).toBe(long);
  });

  it('round-trips through marksFor', () => {
    const arrows = [{ from: 'c6', to: 'd4', brush: 'green' }];
    const parsed = parseCoachMarkup(`Text. ${marksFor(arrows, ['e2'])}`);
    expect(parsed).toEqual({ text: 'Text.', arrows, squares: ['e2'] });
  });
});
