// @vitest-environment jsdom
//
// Auto-save status line and the "Save now" button of an editable game.
import { describe, it, expect, vi, afterEach } from 'vitest';
import { render, screen, fireEvent, cleanup } from '@testing-library/react';
import React from 'react';

vi.mock('next-intl', () => ({
  useTranslations: () => (key: string) => key,
}));

vi.mock('../ShareGameButton', () => ({ default: () => null }));
vi.mock('../SourceBadge', () => ({ default: () => null }));

import GameViewerPanel, { type OpenedGame } from '../GameViewerPanel';
import type { SaveStatus } from '../useAutoSave';

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

const game: OpenedGame = {
  id: 'g-1', white: 'Carlsen', black: 'Nepo', result: '1-0', pgn: '1. e4', moves: ['e4'],
  fens: [], startingFen: START, source: 'user',
};

function renderPanel(props: { saveStatus?: SaveStatus; onRetrySave?: () => void; editIsDirty?: boolean; onEditSave?: () => void }) {
  return render(
    <GameViewerPanel game={game} currentMoveIndex={-1} onMoveIndexChange={vi.fn()} isEditable {...props} />,
  );
}

afterEach(() => cleanup());

describe('GameViewerPanel — auto-save status', () => {
  it('shows nothing while idle', () => {
    renderPanel({ saveStatus: 'idle' });
    expect(screen.queryByRole('status')).toBeNull();
  });

  it('shows Saving…', () => {
    renderPanel({ saveStatus: 'saving' });
    expect(screen.getByRole('status').textContent).toContain('myGames.autoSave.saving');
  });

  it('shows Saved ✓', () => {
    renderPanel({ saveStatus: 'saved' });
    expect(screen.getByRole('status').textContent).toContain('myGames.autoSave.saved ✓');
  });

  it("shows Couldn't save with a Retry button", () => {
    const onRetrySave = vi.fn();
    renderPanel({ saveStatus: 'error', onRetrySave });
    expect(screen.getByRole('status').textContent).toContain('myGames.autoSave.saveFailed');
    fireEvent.click(screen.getByRole('button', { name: 'myGames.autoSave.retry' }));
    expect(onRetrySave).toHaveBeenCalledTimes(1);
  });

  it('labels the manual button "Save now"', () => {
    const onEditSave = vi.fn();
    renderPanel({ editIsDirty: true, onEditSave });
    fireEvent.click(screen.getByRole('button', { name: /myGames\.autoSave\.saveNow/ }));
    expect(onEditSave).toHaveBeenCalledTimes(1);
  });
});
