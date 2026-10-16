// @vitest-environment jsdom
//
// Variations (event 'Variation' or an unsaved draft) show an editable title in
// place of the players / result header; normal games keep the header.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('../ShareGameButton', () => ({ default: () => null }));
vi.mock('../SourceBadge', () => ({ default: () => null }));

import GameViewerPanel, { type OpenedGame } from '../GameViewerPanel';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

const normal: OpenedGame = {
  id: 'g-1', white: 'Carlsen', black: 'Nepo', result: '1-0', date: '2021.12.03',
  event: 'World Championship', pgn: '1. e4', moves: ['e4'], fens: [], startingFen: START, source: 'user',
};

const variation: OpenedGame = { ...normal, id: 'g-2', white: '?', black: '?', result: '*', date: undefined, event: 'Variation', title: 'Najdorf idea' };

function renderPanel(game: OpenedGame, onTitleChange?: (t: string | null) => void) {
  return render(
    <GameViewerPanel game={game} currentMoveIndex={-1} onMoveIndexChange={vi.fn()} onTitleChange={onTitleChange} />,
  );
}

afterEach(() => cleanup());

describe('GameViewerPanel — variation title header', () => {
  it('renders the title instead of players and result', () => {
    renderPanel(variation);
    expect(screen.getByText('Najdorf idea')).toBeTruthy();
    expect(screen.queryByText(/vs/)).toBeNull();
    expect(screen.queryByText('*')).toBeNull();
    expect(screen.queryByText(/Variation/)).toBeNull();
  });

  it('keeps the players / result header for normal games', () => {
    renderPanel(normal);
    expect(screen.getByText(/Carlsen.*vs.*Nepo/)).toBeTruthy();
    expect(screen.getAllByText('1-0').length).toBeGreaterThan(0);
    expect(screen.getByText('2021.12.03')).toBeTruthy();
    expect(screen.queryByLabelText('myGames.editTitle')).toBeNull();
  });

  it('falls back to "Untitled variation" for an untitled draft', () => {
    renderPanel({ ...variation, event: undefined, title: undefined, isDraft: true });
    expect(screen.getByText('myGames.untitledVariation')).toBeTruthy();
  });

  it('hides the Edit button without a handler', () => {
    renderPanel(variation);
    expect(screen.queryByLabelText('myGames.editTitle')).toBeNull();
  });
});

describe('GameViewerPanel — title edit', () => {
  it('Enter commits the trimmed title', () => {
    const onTitleChange = vi.fn();
    renderPanel(variation, onTitleChange);
    fireEvent.click(screen.getByLabelText('myGames.editTitle'));
    const input = screen.getByLabelText('myGames.titlePlaceholder') as HTMLInputElement;
    expect(input.value).toBe('Najdorf idea');
    expect(input.maxLength).toBe(120);
    fireEvent.change(input, { target: { value: '  English Attack  ' } });
    fireEvent.keyDown(input, { key: 'Enter' });
    expect(onTitleChange).toHaveBeenCalledWith('English Attack');
    expect(screen.queryByLabelText('myGames.titlePlaceholder')).toBeNull();
  });

  it('blur commits; an empty title clears to null', () => {
    const onTitleChange = vi.fn();
    renderPanel(variation, onTitleChange);
    fireEvent.click(screen.getByLabelText('myGames.editTitle'));
    const input = screen.getByLabelText('myGames.titlePlaceholder');
    fireEvent.change(input, { target: { value: '   ' } });
    fireEvent.blur(input);
    expect(onTitleChange).toHaveBeenCalledWith(null);
  });

  it('Escape cancels without calling the handler', () => {
    const onTitleChange = vi.fn();
    renderPanel(variation, onTitleChange);
    fireEvent.click(screen.getByLabelText('myGames.editTitle'));
    const input = screen.getByLabelText('myGames.titlePlaceholder');
    fireEvent.change(input, { target: { value: 'Something else' } });
    fireEvent.keyDown(input, { key: 'Escape' });
    expect(screen.queryByLabelText('myGames.titlePlaceholder')).toBeNull();
    expect(screen.getByText('Najdorf idea')).toBeTruthy();
    expect(onTitleChange).not.toHaveBeenCalled();
  });

  it('an unchanged title commits nothing', () => {
    const onTitleChange = vi.fn();
    renderPanel(variation, onTitleChange);
    fireEvent.click(screen.getByLabelText('myGames.editTitle'));
    fireEvent.keyDown(screen.getByLabelText('myGames.titlePlaceholder'), { key: 'Enter' });
    expect(onTitleChange).not.toHaveBeenCalled();
  });
});
