// @vitest-environment jsdom
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, within } from '@testing-library/react';
import React from 'react';

// next-intl: echo the key (with the interpolated name) so assertions stay
// locale-independent while still exercising the linkage logic.
vi.mock('next-intl', () => ({
  useTranslations: () => (key: string, vars?: Record<string, unknown>) =>
    vars?.name ? `${key}:${vars.name}` : key,
}));

import MasterGamesFilter, { MasterGamesFilterState } from '../MasterGamesFilter';

const baseFilters: MasterGamesFilterState = {
  playerName: 'Carlsen',
  opponentName: 'Firouzja',
  playerColor: '',
  result: '',
  sortBy: 'rating',
  whiteEloMin: 0,
  whiteEloMax: 3500,
  blackEloMin: 0,
  blackEloMax: 3500,
  dateFrom: '',
  dateTo: '',
  ecoCode: '',
  eventName: '',
};

/** The two color segmented toggles, in field order [player, opponent]. */
function getToggles() {
  const anyChips = screen.getAllByText('colorAny');
  return anyChips.map((el) => el.closest('div')!.parentElement!);
}

describe('MasterGamesFilter color toggle linkage', () => {
  it('clicking player ♔ sets playerColor=white', () => {
    const onFilterChange = vi.fn();
    render(<MasterGamesFilter filters={baseFilters} onFilterChange={onFilterChange} />);

    const [playerToggle] = getToggles();
    fireEvent.click(within(playerToggle).getByText('♔'));

    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({ playerColor: 'white' }),
    );
  });

  it('opponent toggle displays the inverse of playerColor (player white → opponent ♚ active)', () => {
    // When playerColor is unset the opponent ♚ is inactive; when the player is
    // white it must switch to its active styling — proving the inverse display.
    const { rerender } = render(
      <MasterGamesFilter filters={baseFilters} onFilterChange={vi.fn()} />,
    );
    const inactiveClass = within(getToggles()[1]).getByText('♚').className;

    rerender(
      <MasterGamesFilter
        filters={{ ...baseFilters, playerColor: 'white' }}
        onFilterChange={vi.fn()}
      />,
    );
    const activeClass = within(getToggles()[1]).getByText('♚').className;

    expect(activeClass).not.toEqual(inactiveClass);
  });

  it('clicking opponent ♔ sets playerColor=black (inverse mapping)', () => {
    const onFilterChange = vi.fn();
    render(<MasterGamesFilter filters={baseFilters} onFilterChange={onFilterChange} />);

    const [, opponentToggle] = getToggles();
    fireEvent.click(within(opponentToggle).getByText('♔'));

    expect(onFilterChange).toHaveBeenCalledWith(
      expect.objectContaining({ playerColor: 'black' }),
    );
  });

  it('shows the linked hint once a color is active', () => {
    const onFilterChange = vi.fn();
    const { rerender } = render(
      <MasterGamesFilter filters={baseFilters} onFilterChange={onFilterChange} />,
    );
    expect(screen.queryByText('colorsLinked')).toBeNull();

    const [playerToggle] = getToggles();
    fireEvent.click(within(playerToggle).getByText('♔'));
    // Parent would push the new playerColor back down as a prop.
    rerender(
      <MasterGamesFilter
        filters={{ ...baseFilters, playerColor: 'white' }}
        onFilterChange={onFilterChange}
      />,
    );
    expect(screen.getByText('colorsLinked')).toBeTruthy();
  });
});
