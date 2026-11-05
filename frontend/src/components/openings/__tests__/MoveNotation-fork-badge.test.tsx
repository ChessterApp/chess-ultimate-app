// @vitest-environment jsdom
//
// A move with two or more continuations gets a small "⑂N" badge after it.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, cleanup } from '@testing-library/react';
import React from 'react';
import MoveNotation from '../MoveNotation';
import { pgnToTree } from '@/hooks/useGameMoveTree';

afterEach(() => cleanup());

function setup(pgn: string) {
  render(<MoveNotation tree={pgnToTree(pgn)} selectedNodeId={null} onNodeSelect={vi.fn()} loading={false} />);
}

describe('MoveNotation fork badge', () => {
  it('marks the move a fork starts from with its continuation count', () => {
    setup('1. e4 e5 2. Nf3 (2. Bc4) (2. Nc3) Nc6 *');
    const badges = screen.getAllByTestId('fork-badge');
    expect(badges.map(b => b.textContent)).toEqual(['⑂3']);
    const e5 = screen.getByText('e5');
    expect(e5.compareDocumentPosition(badges[0]) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    // The badge sits outside the move's own text.
    expect(e5.textContent).toBe('e5');
  });

  it('shows no badge without forks', () => {
    setup('1. e4 e5 2. Nf3 *');
    expect(screen.queryByTestId('fork-badge')).toBeNull();
  });
});
