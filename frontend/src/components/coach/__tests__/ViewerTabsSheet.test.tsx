/**
 * @vitest-environment jsdom
 */
import React from 'react';
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup, fireEvent, within } from '@testing-library/react';
import { NextIntlClientProvider } from 'next-intl';

import en from '../../../../messages/en.json';
import ViewerTabsSheet from '../ViewerTabsSheet';
import ViewerMoveList from '../ViewerMoveList';

const coach = en.coach;

function wrap(node: React.ReactElement) {
  return render(
    <NextIntlClientProvider locale="en" messages={en as Record<string, unknown>}>
      {node}
    </NextIntlClientProvider>,
  );
}

afterEach(cleanup);

const tabs = [
  { id: 'g1', title: 'Kasparov vs Topalov', subtitle: '1-0 · Wijk aan Zee' },
  { id: 'g2', title: 'You vs Coach' },
];

describe('ViewerTabsSheet', () => {
  it('a stack chip counts the boards (coach board + games) and names the shown one', () => {
    wrap(<ViewerTabsSheet tabs={tabs} activeId="g1" onSelect={vi.fn()} onClose={vi.fn()} />);
    const chip = screen.getByTestId('viewer-tabs-chip');
    expect(chip.getAttribute('aria-label')).toBe('Open boards: 3');
    expect(chip.textContent).toContain('Kasparov vs Topalov');
  });

  it('the sheet switches boards and closes games', () => {
    const onSelect = vi.fn();
    const onClose = vi.fn();
    wrap(<ViewerTabsSheet tabs={tabs} activeId={null} onSelect={onSelect} onClose={onClose} />);
    fireEvent.click(screen.getByTestId('viewer-tabs-chip'));
    const sheet = within(screen.getByRole('dialog'));
    fireEvent.click(sheet.getByRole('button', { name: `${coach.closeTab}: You vs Coach` }));
    expect(onClose).toHaveBeenCalledWith('g2');
    fireEvent.click(sheet.getByText('Kasparov vs Topalov'));
    expect(onSelect).toHaveBeenCalledWith('g1');
    // Picking closes the sheet.
    expect(screen.queryByRole('dialog')).toBeNull();
  });

  it('the coach board is listed first and Esc closes the sheet', () => {
    const onSelect = vi.fn();
    wrap(<ViewerTabsSheet tabs={tabs} activeId="g1" onSelect={onSelect} onClose={vi.fn()} />);
    fireEvent.click(screen.getByTestId('viewer-tabs-chip'));
    fireEvent.keyDown(window, { key: 'Escape' });
    expect(screen.queryByRole('dialog')).toBeNull();
    fireEvent.click(screen.getByTestId('viewer-tabs-chip'));
    fireEvent.click(within(screen.getByRole('dialog')).getByText(coach.coachBoard));
    expect(onSelect).toHaveBeenCalledWith(null);
  });
});

describe('ViewerMoveList', () => {
  const moves = ['e4', 'c5', 'Nf3', 'd6', 'd4'];

  it('tap a move to jump there; the current one is marked', () => {
    const onJump = vi.fn();
    wrap(<ViewerMoveList moves={moves} currentIndex={2} onJump={onJump} />);
    expect(screen.getByText('Nf3').getAttribute('aria-current')).toBe('true');
    fireEvent.click(screen.getByText('d6'));
    expect(onJump).toHaveBeenCalledWith(3);
    expect(screen.getByText('3.')).toBeTruthy();
  });

  it('list layout: numbered rows', () => {
    wrap(<ViewerMoveList moves={moves} currentIndex={-1} onJump={vi.fn()} layout="list" />);
    expect(screen.getAllByRole('listitem')).toHaveLength(3);
    expect(screen.queryByRole('button', { current: true })).toBeNull();
  });
});
