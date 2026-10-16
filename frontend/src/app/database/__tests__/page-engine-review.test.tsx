// @vitest-environment jsdom
//
// Database page: no "Review this game" on opened games; the Stockfish toggle,
// eval bar and best line work on every tab (master games, own games, analysis
// lines, shared read-only databases, the empty My Games board) and analyse the
// shown position; the on/off state survives tab switches but is never written
// to storage (auto-enable on reload is a WASM crash loop). Every child panel is
// stubbed; the page's own wiring is real.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
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
let repertoire: Record<string, unknown> | null = null;
vi.mock('@/hooks/useOpeningRepertoire', () => ({
  useOpeningRepertoire: () => repertoire ??= ({
    repertoires: [], loading: false, error: null, fetchRepertoires: vi.fn(),
    createRepertoire: noopAsync, updateRepertoire: noopAsync, deleteRepertoire: noopAsync,
    currentTree: null, setCurrentTree: vi.fn(), treeLoading: false, fetchTree: noopAsync,
    addNode: noopAsync, updateNode: noopAsync, deleteNode: noopAsync,
    importPgn: noopAsync, exportPgn: noopAsync, addArrow: noopAsync, deleteArrow: noopAsync,
    fetchGamesByPosition: neverAsync, fetchPositionCount: neverAsync, fetchGamePgn: noopAsync, fetchLichessPgn: noopAsync,
    searchGamesStream: vi.fn(), linkGame: noopAsync, getNodeGames: neverAsync, deleteGameLink: noopAsync,
    fetchCandidateMoves: neverAsync,
  }),
}));
const analyze = vi.fn();
const stopAnalysis = vi.fn();
const engineOn = {
  evaluation: { lines: [{ cp: 35, pv: ['e7e5'], depth: 14 }] },
  isAnalyzing: false, isReady: true, depth: 14, engineError: null, engineName: 'sf17', analyze, stopAnalysis,
};
const engineOff = { ...engineOn, evaluation: null, depth: 0 };
vi.mock('@/hooks/useReplayStockfish', () => ({
  useReplayStockfish: ({ enabled }: { enabled: boolean }) => (enabled ? engineOn : engineOff),
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
vi.mock('@/components/opponent/ReplayEngineLines', () => stub('engine-lines'));
vi.mock('@/components/openings/RepertoireSelector', () => stub('repertoire-selector'));
vi.mock('@/components/openings/MoveNotation', () => stub('move-notation'));
vi.mock('@/components/openings/NodeDetailsPanel', () => stub('node-details'));
vi.mock('@/components/openings/MoveTree', () => stub('move-tree'));
vi.mock('@/components/openings/PositionSummary', () => stub('position-summary'));
vi.mock('@/components/openings/PgnImporter', () => stub('pgn-importer'));
vi.mock('@/components/openings/GameSearchPanel', () => stub('game-search'));
vi.mock('@/components/analysis/TwicExplorer', () => stub('twic'));
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
  default: ({ onOpenGame }: { onOpenGame: (g: unknown) => void }) => (
    <div data-testid="my-games-panel">
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

const engineSwitch = () => screen.getByRole('switch');

beforeEach(() => {
  analyze.mockReset();
  voiceHook.mockReset();
  global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
  window.innerWidth = 1280;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Database page — Review button', () => {
  it('is not shown for opened own games, analysis lines or shared games', async () => {
    await renderPage();
    await click('pick own db');
    for (const name of ['open own game', 'open variation']) {
      await click(name);
      expect(screen.getAllByTestId('game-viewer').length).toBeGreaterThan(0);
      expect(screen.queryByText(/review this game/i)).toBeNull();
      await click('pick own db');
    }
    await click('pick shared db');
    await click('open shared game');
    expect(screen.queryByText(/review this game/i)).toBeNull();
  });
});

describe('Database page — engine + eval bar everywhere', () => {
  it('is off by default and turns on on the empty My Games board', async () => {
    await renderPage();
    await click('pick own db');
    expect(screen.queryByTestId('eval-bar')).toBeNull();
    await act(async () => { fireEvent.click(engineSwitch()); });
    expect(screen.getByTestId('eval-bar')).toBeTruthy();
    expect(screen.getByText('+0.3')).toBeTruthy();
    expect(screen.getByTestId('engine-lines')).toBeTruthy();
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
    expect(screen.getByText('+0.3')).toBeTruthy();
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
