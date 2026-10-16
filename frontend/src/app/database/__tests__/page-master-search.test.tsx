// @vitest-environment jsdom
//
// Database page, Master tab: the board's only job is to reach a position and
// auto-search the Master games database for it. Every move, candidate click and
// back/start/reset step re-runs /games/by-position (+ exact-count refinement)
// and /positions/candidates through the authenticated fetch, with the active
// filters applied. Nothing is saved; there is no repertoire UI. The real
// useMasterGames hook runs against a stubbed apiFetch.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, act } from '@testing-library/react';
import React, { Suspense } from 'react';

vi.mock('next/dynamic', () => ({
  default: (loader: () => Promise<{ default: React.ComponentType<any> }>) => {
    const Lazy = React.lazy(loader);
    return function Dynamic(props: any) { return <Lazy {...props} />; };
  },
}));
const searchParams = new URLSearchParams();
vi.mock('next/navigation', () => ({ useSearchParams: () => searchParams }));
const translate = (key: string) => key;
vi.mock('next-intl', () => ({ useTranslations: () => translate }));
const getToken = vi.fn(async () => 'tok');
const auth = { isLoaded: true, isSignedIn: true, getToken };
vi.mock('@clerk/nextjs', () => ({ useAuth: () => auth }));

type Call = { path: string; params: URLSearchParams; headers: Record<string, string> };
const calls: Call[] = [];
const apiFetch = vi.fn(async (url: string, opts?: { headers?: Record<string, string> }) => {
  const [path, qs] = url.split('?');
  calls.push({ path, params: new URLSearchParams(qs), headers: opts?.headers ?? {} });
  if (path.endsWith('/games/by-position')) {
    return { games: [{ id: 1, white: 'A', black: 'B' }], total: 100, indexed: true, count_exact: false };
  }
  if (path.endsWith('/games/position-count')) return { count: 4321 };
  if (path.endsWith('/positions/candidates')) {
    return { status: 'ok', total_games: 100, moves: [{ uci: 'e7e5', san: 'e5', count: 60 }, { uci: '', san: 'c5', count: 40 }] };
  }
  return new Promise(() => {});
});
vi.mock('@/lib/api', () => ({ apiFetch: (...a: [string, any]) => apiFetch(...a), ApiError: class extends Error {} }));
vi.mock('@/hooks/useBackendHealth', () => ({ useBackendHealth: () => true }));
const lichess = { data: null, loading: false };
vi.mock('@/hooks/useLichessExplorer', () => ({ useLichessExplorer: () => lichess }));
const userGames = { createGame: vi.fn(), updateGame: vi.fn(), toggleFavorite: vi.fn(), deleteGame: vi.fn() };
vi.mock('@/hooks/useUserGames', () => ({ useUserGames: () => userGames }));
const engineOff = {
  evaluation: null, isAnalyzing: false, isReady: false, depth: 0, engineError: null, engineName: 'sf17',
  analyze: vi.fn(), stopAnalysis: vi.fn(),
};
vi.mock('@/hooks/useReplayStockfish', () => ({ useReplayStockfish: () => engineOff }));
const voiceNotes = { notes: [], paths: new Set(), playingPath: null, save: vi.fn(), remove: vi.fn(), removeFrom: vi.fn(), toggle: vi.fn() };
vi.mock('@/hooks/useMoveVoiceNotes', () => ({ useMoveVoiceNotes: () => voiceNotes }));
vi.mock('@/lib/openingdatabase/ecoDatabase', () => ({
  findEcoOpening: async (fen: string) => (fen.startsWith('rnbqkbnr/pppppppp/8/8/4P3/') ? { eco: 'B00', name: "King's Pawn Game" } : null),
}));

// ─── Stubbed panels ──────────────────────────────────────────────────────────
const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const AFTER_E4 = 'rnbqkbnr/pppppppp/8/8/4P3/8/PPPP1PPP/RNBQKBNR b KQkq - 0 1';
const AFTER_E4_E5 = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2';
const AFTER_E4_C5 = 'rnbqkbnr/pp1ppppp/8/2p5/4P3/8/PPPP1PPP/RNBQKBNR w KQkq - 0 2';

const stub = (testId: string) => ({ default: () => <div data-testid={testId} /> });
vi.mock('@/components/openings/DebutBoard', () => ({
  default: (p: any) => (
    <div data-testid="board" data-fen={p.fen}>
      <button onClick={() => p.onMove('e2', 'e4', 'P', AFTER_E4, 'e4', 'e2e4')}>play e4</button>
      <button onClick={() => p.onPrev()}>prev</button>
      <button onClick={() => p.onNext()}>next</button>
      <button onClick={() => p.onGoToStart()}>start</button>
      <button onClick={() => p.onReset()}>reset</button>
    </div>
  ),
}));
vi.mock('@/components/opponent/ReplayEvalBar', () => stub('eval-bar'));
vi.mock('@/components/opponent/ReplayEngineLines', () => stub('engine-lines'));
vi.mock('@/components/openings/MoveTree', () => ({
  default: (p: any) => (
    <div data-testid="move-tree" data-fen={p.fen}>
      {p.moves.map((m: any) => <button key={m.san} onClick={() => p.onMoveClick(m)}>{`cand ${m.san}`}</button>)}
    </div>
  ),
}));
vi.mock('@/components/openings/PositionSummary', () => ({
  default: (p: any) => <div data-testid="position-summary">{`${p.ecoCode ?? ''}|${p.openingName ?? ''}`}</div>,
}));
vi.mock('@/components/openings/MasterGamesPanel', () => ({
  default: (p: any) => (
    <div data-testid="master-games" data-fen={p.fen} data-total={p.masterGamesTotal}>
      <button onClick={() => p.onMasterGamesFilterChange({ ...p.masterGamesFilters, playerName: 'Carlsen', result: '1-0', ecoCode: 'C20' })}>
        filter carlsen
      </button>
    </div>
  ),
}));
vi.mock('@/components/openings/MyGamesPanel', () => stub('my-games-panel'));
vi.mock('@/components/openings/MyGamesMoveList', () => stub('my-games-move-list'));
vi.mock('@/components/openings/EditGameModal', () => stub('edit-modal'));
vi.mock('@/components/openings/GameViewerPanel', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/openings/GameViewerPanel')>();
  return { ...actual, default: () => <div data-testid="game-viewer" /> };
});
vi.mock('@/components/openings/DatabasePillRow', () => ({ default: () => null }));

import DebutPage from '../page';

async function renderPage() {
  await act(async () => {
    render(<Suspense fallback={null}><DebutPage /></Suspense>);
  });
}

async function click(name: string) {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name })); });
}

const callsFor = (suffix: string) => calls.filter(c => c.path.endsWith(suffix));
const lastFor = (suffix: string) => callsFor(suffix).at(-1)!;
const boardFen = () => screen.getByTestId('board').getAttribute('data-fen');

beforeEach(() => {
  calls.length = 0;
  apiFetch.mockClear();
  getToken.mockClear();
  global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
  window.innerWidth = 1280;
});

afterEach(() => {
  cleanup();
});

describe('Database page — Master tab auto-search', () => {
  it('searches the starting position on load through the authenticated API', async () => {
    await renderPage();
    expect(boardFen()).toBe(START);
    for (const suffix of ['/games/by-position', '/positions/candidates']) {
      const call = lastFor(suffix);
      expect(call.path).toBe(`/api/openings${suffix}`);
      expect(call.params.get('fen')).toBe(START);
      expect(call.headers.Authorization).toBe('Bearer tok');
    }
    expect(getToken).toHaveBeenCalled();
  });

  it('a board move re-runs games, exact count and candidates for the new FEN', async () => {
    await renderPage();
    calls.length = 0;
    await click('play e4');

    expect(boardFen()).toBe(AFTER_E4);
    expect(screen.getByTestId('master-games').getAttribute('data-fen')).toBe(AFTER_E4);
    expect(lastFor('/games/by-position').params.get('fen')).toBe(AFTER_E4);
    expect(lastFor('/positions/candidates').params.get('fen')).toBe(AFTER_E4);
    // Estimated total is refined by the authenticated exact count.
    expect(lastFor('/games/position-count').params.get('fen')).toBe(AFTER_E4);
    expect(lastFor('/games/position-count').headers.Authorization).toBe('Bearer tok');
    expect(screen.getByTestId('master-games').getAttribute('data-total')).toBe('4321');
  });

  it('keeps the active filters on the query when the position changes', async () => {
    await renderPage();
    await click('filter carlsen');
    calls.length = 0;
    await click('play e4');

    const params = lastFor('/games/by-position').params;
    expect(params.get('fen')).toBe(AFTER_E4);
    expect(params.get('player_name')).toBe('Carlsen');
    expect(params.get('result')).toBe('1-0');
    expect(params.get('eco_code')).toBe('C20');
    expect(lastFor('/games/by-position').headers.Authorization).toBe('Bearer tok');
  });

  it('clicking a candidate move plays it (uci or SAN-only) and re-fetches', async () => {
    await renderPage();
    await click('play e4');
    await click('cand e5');
    expect(boardFen()).toBe(AFTER_E4_E5);
    expect(lastFor('/games/by-position').params.get('fen')).toBe(AFTER_E4_E5);
    expect(lastFor('/positions/candidates').params.get('fen')).toBe(AFTER_E4_E5);

    // Back, then a SAN-only candidate (empty uci) branches off.
    await click('prev');
    await click('cand c5');
    expect(boardFen()).toBe(AFTER_E4_C5);
    expect(lastFor('/games/by-position').params.get('fen')).toBe(AFTER_E4_C5);
  });

  it('back / forward / start / reset step through the in-memory history and the results follow', async () => {
    await renderPage();
    await click('play e4');
    await click('cand e5');

    calls.length = 0;
    await click('prev');
    expect(boardFen()).toBe(AFTER_E4);
    expect(lastFor('/games/by-position').params.get('fen')).toBe(AFTER_E4);
    expect(lastFor('/positions/candidates').params.get('fen')).toBe(AFTER_E4);

    await click('next');
    expect(boardFen()).toBe(AFTER_E4_E5);

    await click('start');
    expect(boardFen()).toBe(START);
    expect(lastFor('/games/by-position').params.get('fen')).toBe(START);

    await click('next');
    expect(boardFen()).toBe(AFTER_E4);

    await click('reset');
    expect(boardFen()).toBe(START);
    await click('next');
    expect(boardFen()).toBe(START); // reset cleared the forward history
  });

  it('labels the opening from the board position, keeping the last named one deeper in the line', async () => {
    await renderPage();
    expect(screen.getByTestId('position-summary').textContent).toBe('|');
    await click('play e4');
    expect(screen.getByTestId('position-summary').textContent).toBe("B00|King's Pawn Game");
    await click('cand e5');
    expect(screen.getByTestId('position-summary').textContent).toBe("B00|King's Pawn Game");
  });

  it('saves nothing and shows no repertoire UI or repertoire move list', async () => {
    await renderPage();
    await click('play e4');
    expect(screen.queryByText(/repertoire/i)).toBeNull();
    expect(screen.queryByText('Make a move on the board to start.')).toBeNull();
    expect(calls.some(c => /\/(repertoires|nodes|training)/.test(c.path))).toBe(false);
    expect(apiFetch.mock.calls.every(([, opts]) => !opts || !('method' in opts) || opts.method === 'GET')).toBe(true);
  });
});
