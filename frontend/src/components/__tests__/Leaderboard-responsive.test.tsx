// @vitest-environment jsdom
import { describe, it, expect } from 'vitest';
import { render } from '@testing-library/react';
import React from 'react';
import Leaderboard from '../ratings/Leaderboard';

const entries = [
  {
    user_id: 'u1',
    rating: 1500,
    league: 'silver',
    games_played: 42,
    is_provisional: false,
    peak_rating: 1600,
    player_name: 'Alice',
  },
];

describe('Leaderboard responsive overflow', () => {
  it('wraps the table in an overflow-x-auto container', () => {
    const { container } = render(<Leaderboard entries={entries} />);
    const wrapper = container.querySelector('.overflow-x-auto');
    expect(wrapper).toBeTruthy();
    expect(wrapper!.querySelector('table')).toBeTruthy();
  });

  it('hides secondary columns on small screens', () => {
    const { container } = render(<Leaderboard entries={entries} />);
    const hiddenCells = container.querySelectorAll('.hidden.sm\\:table-cell');
    // Games + Peak header and body cells
    expect(hiddenCells.length).toBeGreaterThanOrEqual(2);
  });
});
