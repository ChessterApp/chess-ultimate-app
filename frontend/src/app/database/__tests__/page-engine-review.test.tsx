// @vitest-environment jsdom
//
// Database page: every opened game with moves shows Review (master, own,
// analysis line, shared); the Stockfish toggle,
// eval bar and engine lines work on every tab (master games, own games, analysis
// lines, shared read-only databases, the empty My Games board) and analyse the
// shown position; the on/off state survives tab switches but is never written
// to storage (auto-enable on reload is a WASM crash loop). Engine depth/lines
// come from the shared display settings and the gear never toggles the engine.
// Every child panel except the engine lines is stubbed; the page's own wiring
// is real.
import { describe, it, expect, vi, afterEach, beforeEach, beforeAll } from 'vitest';
import { render, screen, fireEvent, cleanup, act, within } from '@testing-library/react';
import React, { Suspense } from 'react';

vi.mock('next/dynamic', () => ({
  default: (loader: () => Promise<{ default: React.ComponentType<any> }>) => {
    const Lazy = React.lazy(loader);
    return function Dynamic(props: any) { return <Lazy {...props} />; };
  },
}));
// Real hooks hand back stable references; fresh ones per render would re-fire
// the page's fetch effects forever.
const searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({ useSearchParams: () => searchParams }));
const translate = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => translate }));
const auth = { isLoaded: true, isSignedIn: true, getToken: async () => 'tok' };
vi.mock('@clerk/nextjs', () => ({ useAuth: () => auth }));
vi.mock('@/lib/api', () => ({ apiFetch: vi.fn(() => new Promise(() => {})), ApiError: class extends Error {} }));
vi.mock('@/hooks/useBackendHealth', () => ({ useBackendHealth: () => true }));
const lichess = { data: null, loading: false };
vi.mock('@/hooks/useLichessExplorer', () => ({ useLichessExplorer: () => lichess }));
const userGames = { createGame: vi.fn(), updateGame: vi.fn(), toggleFavorite: vi.fn(), deleteGame: vi.fn() };
vi.mock('@/hooks/useUserGames', () => ({ useUserGames: () => userGames }));
const noopAsync = () => Promise.resolve(null as any);
const neverAsync = () => new Promise<any>(() => {});
const masterGames = {
  fetchGamesByPosition: neverAsync, fetchPositionCount: neverAsync, fetchCandidateMoves: neverAsync,
  fetchGamePgn: noopAsync, fetchLichessPgn: noopAsync,
};
vi.mock('@/hooks/useMasterGames', () => ({ useMasterGames: () => masterGames }));
vi.mock('@/lib/openingdatabase/ecoDatabase', () => ({ findEcoOpening: async () => null }));
const analyze = vi.fn();
const stopAnalysis = vi.fn();
const engineOn = {
  evaluation: {
    lines: [
      { cp: 35, pv: ['e2e4', 'e7e5', 'g1f3', 'b8c6', 'f1b5', 'a7a6', 'b5a4', 'g8f6', 'e1g1'], depth: 14 },
      { cp: 30, pv: ['d2d4', 'd7d5'], depth: 14 },
      { cp: 20, pv: ['c2c4'], depth: 14 },
    ],
  },
  isAnalyzing: false, isReady: true, depth: 14, engineError: null, engineName: 'sf17', analyze, stopAnalysis,
};
const engineOff = { ...engineOn, evaluation: null, depth: 0 };
const engineOpts = vi.fn();
vi.mock('@/hooks/useReplayStockfish', () => ({
  useReplayStockfish: (opts: { enabled: boolean }) => {
    engineOpts(opts);
    return opts.enabled ? engineOn : engineOff;
  },
}));
const voiceHook = vi.fn();
const voiceNotes = { notes: [], paths: new Set(), playingPath: null, save: vi.fn(), remove: vi.fn(), removeFrom: vi.fn(), toggle: vi.fn() };
vi.mock('@/hooks/useMoveVoiceNotes', () => ({
  useMoveVoiceNotes: (opts: unknown) => {
    voiceHook(opts);
    return voiceNotes;
  },
}));

// ─── Stubbed panels ──────────────────────────────────────────────────────────
const stub = (testId: string) => ({ default: () => <div data-testid={testId} /> });
vi.mock('@/components/openings/DebutBoard', () => ({
  default: (p: { fen: string; reservedWidth?: number }) => (
    <div data-testid="board" data-fen={p.fen} data-reserved={p.reservedWidth ?? 0} />
  ),
}));
vi.mock('@/components/opponent/ReplayEvalBar', () => stub('eval-bar'));
const MASTER_GAME = { id: 'master-1', white: 'Carlsen', black: 'Nakamura', result: '1-0', pgn: '1. e4 c5 2. Nf3 *', source: 'master' };
vi.mock('@/components/openings/MasterGamesPanel', () => ({
  default: ({ onOpenGame }: { onOpenGame: (g: unknown) => void }) => (
    <div data-testid="master-games">
      <button onClick={() => onOpenGame(MASTER_GAME)}>open master game</button>
    </div>
  ),
}));
vi.mock('@/components/review/StartReviewButton', () => ({
  default: (p: { game: { pgn: string; orientation?: string }; source: string; label?: string }) => (
    <button data-testid="start-review-button" data-pgn={p.game.pgn} data-source={p.source} data-label={p.label ?? ''}>review</button>
  ),
}));
vi.mock('@/components/openings/MoveTree', () => stub('move-tree'));
vi.mock('@/components/openings/PositionSummary', () => stub('position-summary'));
vi.mock('@/components/openings/MyGamesMoveList', () => stub('my-games-move-list'));
vi.mock('@/components/openings/EditGameModal', () => stub('edit-modal'));
vi.mock('@/components/openings/DatabasePillRow', () => ({
  default: ({ onSelect }: { onSelect: (id: string | null, token?: string) => void }) => (
    <div>
      <button onClick={() => onSelect('db-1')}>pick own db</button>
      <button onClick={() => onSelect(null, 'share-tok')}>pick shared db</button>
      <button onClick={() => onSelect(null)}>pick master</button>
    </div>
  ),
}));
const OWN_GAME = { id: 'own-1', user_id: 'u1', white: 'Me', black: 'You', result: '1-0', pgn: '1. e4 e5 *', source: 'user' };
const VARIATION = { id: 'var-1', user_id: 'u1', white: '?', black: '?', result: '*', event: 'Variation', title: 'Sicilian', pgn: '1. e4 c5 *', source: 'user' };
const SHARED_GAME = { id: 'shared-1', white: 'Owner', black: 'Friend', result: '*', pgn: '1. d4 d5 *', source: 'user' };
vi.mock('@/components/openings/MyGamesPanel', () => ({
  default: ({ onOpenGame, onAddVariation }: { onOpenGame: (g: unknown) => void; onAddVariation?: () => void }) => (
    <div data-testid="my-games-panel">
      <button onClick={() => onAddVariation?.()}>add variation</button>
      <button onClick={() => onOpenGame(OWN_GAME)}>open own game</button>
      <button onClick={() => onOpenGame(VARIATION)}>open variation</button>
      <button onClick={() => onOpenGame(SHARED_GAME)}>open shared game</button>
    </div>
  ),
}));
vi.mock('@/components/openings/GameViewerPanel', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/openings/GameViewerPanel')>();
  return {
    ...actual,
    default: (p: any) => (
      <div
        data-testid="game-viewer"
        data-game={p.game.id}
        data-editable={String(!!p.isEditable)}
        data-tree={String(!!p.editTree)}
        data-edit-actions={String(!!p.editContextMenuActions)}
        data-voice={String(!!p.voiceNotes)}
      />
    ),
  };
});

import DebutPage from '../page';

async function renderPage() {
  await act(async () => {
    render(<Suspense fallback={null}><DebutPage /></Suspense>);
  });
}

async function click(name: string) {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name })); });
}

// `hidden`: an open gear popover aria-hides the page behind it.
const engineSwitch = () => screen.getByRole('switch', { hidden: true });

// The real engine-lines panel is lazy-loaded; warm it so it never suspends the page mid-test.
beforeAll(async () => {
  await import('@/components/opponent/ReplayEngineLines');
});

beforeEach(() => {
  window.localStorage.clear();
  analyze.mockReset();
  engineOpts.mockReset();
  voiceHook.mockReset();
  global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
  window.innerWidth = 1280;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Database page — Review button', () => {
  const reviewButton = () => screen.queryByTestId('start-review-button');

  it('is shown for an opened master game, with its PGN and the always-allowed database source', async () => {
    await renderPage();
    await click('pick master');
    await click('open master game');
    const btn = reviewButton()!;
    expect(btn).toBeTruthy();
    expect(btn.getAttribute('data-pgn')).toBe(MASTER_GAME.pgn);
    expect(btn.getAttribute('data-source')).toBe('database');
    // No hardcoded English label: the translated default is used.
    expect(btn.getAttribute('data-label')).toBe('');
  });

  it('is shown for opened own games, analysis lines and shared games', async () => {
    await renderPage();
    await click('pick own db');
    for (const name of ['open own game', 'open variation']) {
      await click(name);
      expect(screen.getAllByTestId('game-viewer').length).toBeGreaterThan(0);
      expect(reviewButton()).toBeTruthy();
      await click('pick own db');
    }
    await click('pick shared db');
    await click('open shared game');
    expect(reviewButton()?.getAttribute('data-pgn')).toBe(SHARED_GAME.pgn);
  });

  it('is hidden on an empty variation draft and on the explorer tab', async () => {
    await renderPage();
    expect(reviewButton()).toBeNull();
    await click('pick own db');
    await click('add variation');
    expect(screen.getAllByTestId('game-viewer').length).toBeGreaterThan(0);
    expect(reviewButton()).toBeNull();
  });
});

describe('Database page — engine + eval bar everywhere', () => {
  it('is off by default and turns on on the empty My Games board', async () => {
    await renderPage();
    await click('pick own db');
    expect(screen.queryByTestId('eval-bar')).toBeNull();
    await act(async () => { fireEvent.click(engineSwitch()); });
    expect(screen.getByTestId('eval-bar')).toBeTruthy();
    expect(screen.getByTestId('replay-engine-lines')).toBeTruthy();
  });

  it('stays on across own game, analysis line and shared game, analysing the shown position', async () => {
    await renderPage();
    await click('pick own db');
    await act(async () => { fireEvent.click(engineSwitch()); });

    await click('open own game');
    expect(screen.getByTestId('eval-bar')).toBeTruthy();
    expect((engineSwitch() as HTMLInputElement).checked).toBe(true);
    const ownFen = screen.getByTestId('board').getAttribute('data-fen');
    expect(analyze).toHaveBeenLastCalledWith(ownFen);

    await click('pick own db');
    await click('open variation');
    expect(screen.getByTestId('eval-bar')).toBeTruthy();

    await click('pick shared db');
    await click('open shared game');
    expect(screen.getByTestId('eval-bar')).toBeTruthy();
    expect(screen.getByTestId('replay-engine-lines')).toBeTruthy();
    expect(analyze).toHaveBeenLastCalledWith(screen.getByTestId('board').getAttribute('data-fen'));
  });

  it('works on the master (TWIC) tab too', async () => {
    await renderPage();
    await act(async () => { fireEvent.click(engineSwitch()); });
    expect(screen.getByTestId('eval-bar')).toBeTruthy();
    expect(analyze).toHaveBeenCalledWith('rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1');
  });

  it('does not move or resize the board when the eval bar appears', async () => {
    await renderPage();
    const before = {
      reserved: screen.getByTestId('board').getAttribute('data-reserved'),
      anchor: screen.getByTestId('board-anchor').getAttribute('style') + screen.getByTestId('board-anchor').className,
    };
    await act(async () => { fireEvent.click(engineSwitch()); });
    expect(screen.getByTestId('eval-bar')).toBeTruthy();
    expect(screen.getByTestId('board').getAttribute('data-reserved')).toBe(before.reserved);
    expect(screen.getByTestId('board-anchor').getAttribute('style') + screen.getByTestId('board-anchor').className).toBe(before.anchor);
  });

  it('never writes the enabled state to localStorage or sessionStorage', async () => {
    const setItem = vi.spyOn(Storage.prototype, 'setItem');
    await renderPage();
    setItem.mockClear();
    await act(async () => { fireEvent.click(engineSwitch()); });
    await click('pick own db');
    await click('open own game');
    expect(setItem).not.toHaveBeenCalled();
  });
});

describe('Database page — engine panel design', () => {
  const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';

  it('shows one numbered line by default, no best-line box, no "Engine Analysis"/"Depth:" header', async () => {
    await renderPage();
    await act(async () => { fireEvent.click(engineSwitch()); });
    expect(engineOpts).toHaveBeenLastCalledWith(expect.objectContaining({ enabled: true, depth: 18, multiPv: 1 }));
    expect(screen.getAllByTestId('engine-line-row')).toHaveLength(1);
    expect(screen.getByTestId('engine-line-moves').textContent).toBe('1.e4 e5 2.Nf3 Nc6 3.Bb5 a6 4.Ba4 Nf6');
    // The old white best-line box rendered a 1-decimal eval ("+0.3") — gone.
    expect(screen.queryByText('+0.3')).toBeNull();
    expect(screen.getAllByText('+0.35')).toHaveLength(1);
    expect(screen.queryByText(/engine analysis/i)).toBeNull();
    expect(screen.queryByText(/depth:/i)).toBeNull();
    expect(analyze).toHaveBeenCalledWith(START);
  });

  it('renders as many lines as the stored setting and passes depth/lines to the engine', async () => {
    window.localStorage.setItem('chesster.engineDisplay.v1', JSON.stringify({ depth: 24, lines: 3 }));
    await renderPage();
    await act(async () => { fireEvent.click(engineSwitch()); });
    expect(engineOpts).toHaveBeenLastCalledWith(expect.objectContaining({ depth: 24, multiPv: 3 }));
    expect(screen.getAllByTestId('engine-line-row')).toHaveLength(3);
  });

  it('shows the label, depth and gear in one row; the gear opens settings without toggling the engine', async () => {
    await renderPage();
    await act(async () => { fireEvent.click(engineSwitch()); });
    const label = screen.getByText('Stockfish 17');
    const gear = screen.getByRole('button', { name: 'settings' });
    const row = label.parentElement!;
    expect(row.contains(gear)).toBe(true);
    expect(row.contains(engineSwitch())).toBe(true);
    // Order: label · d14 → gear → switch.
    const order = Array.from(row.querySelectorAll('*'));
    expect(order.indexOf(label)).toBeLessThan(order.indexOf(gear));
    expect(order.indexOf(gear)).toBeLessThan(order.indexOf(engineSwitch()));
    expect(screen.getByText('· d14')).toBeTruthy();

    await act(async () => { fireEvent.click(gear); });
    expect((engineSwitch() as HTMLInputElement).checked).toBe(true);
    expect(screen.getByRole('group', { name: 'lines' })).toBeTruthy();
  });

  it('changing Lines in the gear menu re-renders with that many lines', async () => {
    await renderPage();
    await act(async () => { fireEvent.click(engineSwitch()); });
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'settings' })); });
    const linesGroup = screen.getByRole('group', { name: 'lines' });
    await act(async () => { fireEvent.click(within(linesGroup).getByRole('button', { name: '2' })); });
    expect((engineSwitch() as HTMLInputElement).checked).toBe(true);
    expect(engineOpts).toHaveBeenLastCalledWith(expect.objectContaining({ multiPv: 2 }));
    expect(screen.getAllByTestId('engine-line-row')).toHaveLength(2);
  });
});

describe('Database page — shared games are read-only', () => {
  it('own games are editable with voice notes; shared games show the tree read-only with playback', async () => {
    await renderPage();
    await click('pick own db');
    await click('open own game');
    let viewer = screen.getAllByTestId('game-viewer')[0];
    expect(viewer.getAttribute('data-editable')).toBe('true');
    expect(viewer.getAttribute('data-edit-actions')).toBe('true');
    expect(viewer.getAttribute('data-voice')).toBe('true');
    expect(voiceHook).toHaveBeenLastCalledWith(expect.objectContaining({ gameId: 'own-1' }));

    await click('pick shared db');
    await click('open shared game');
    viewer = screen.getAllByTestId('game-viewer')[0];
    expect(viewer.getAttribute('data-game')).toBe('shared-1');
    expect(viewer.getAttribute('data-editable')).toBe('false');
    expect(viewer.getAttribute('data-tree')).toBe('true');
    expect(viewer.getAttribute('data-edit-actions')).toBe('false');
    expect(viewer.getAttribute('data-voice')).toBe('true');
    expect(voiceHook).toHaveBeenLastCalledWith(expect.objectContaining({ gameId: 'shared-1', shareToken: 'share-tok' }));
  });
});
