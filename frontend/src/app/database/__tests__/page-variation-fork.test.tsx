// @vitest-environment jsdom
//
// Database page: variation forks in tree mode — picker + Next badge + board
// arrows at a fork, fork memory for Next / Go to end (picker, notation, Next),
// ↑/↓ highlight and 1–9 keys; a game without forks navigates as before.
// Child panels are stubbed; the page's own wiring and the picker are real.
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
  default: (p: any) => (
    <div data-testid="board" data-fen={p.fen} data-next-badge={p.nextBadgeCount ?? ''} data-arrows={JSON.stringify(p.extraAutoShapes ?? [])}>
      <button onClick={p.onNext}>board next</button>
      <button onClick={p.onPrev}>board prev</button>
      <button onClick={p.onGoToStart}>board start</button>
      <button onClick={p.onGoToEnd}>board end</button>
    </div>
  ),
}));
vi.mock('@/components/opponent/ReplayEvalBar', () => stub('eval-bar'));
vi.mock('@/components/opponent/ReplayEngineLines', () => stub('engine-lines'));
vi.mock('@/components/openings/MasterGamesPanel', () => stub('master-games'));
vi.mock('@/components/review/StartReviewButton', () => ({ default: () => <div data-testid="start-review-button" /> }));
vi.mock('@/components/openings/MoveTree', () => stub('move-tree'));
vi.mock('@/components/openings/PositionSummary', () => stub('position-summary'));
vi.mock('@/components/openings/MyGamesMoveList', () => stub('my-games-move-list'));
vi.mock('@/components/openings/EditGameModal', () => stub('edit-modal'));
vi.mock('@/components/openings/DatabasePillRow', () => ({
  default: ({ onSelect }: { onSelect: (id: string | null) => void }) => <button onClick={() => onSelect('db-1')}>pick own db</button>,
}));
const FORK_PGN = '1. e4 e5 (1... c5 2. Nf3 d6) 2. Nf3 Nc6 *';
const FORK_GAME = { id: 'fork-1', user_id: 'u1', white: 'Me', black: 'You', result: '*', pgn: FORK_PGN, source: 'user' };
const PLAIN_PGN = '1. e4 e5 2. Nf3 *';
const PLAIN_GAME = { id: 'plain-1', user_id: 'u1', white: 'Me', black: 'You', result: '*', pgn: PLAIN_PGN, source: 'user' };
vi.mock('@/components/openings/MyGamesPanel', () => ({
  default: ({ onOpenGame }: { onOpenGame: (g: unknown) => void }) => (
    <div>
      <button onClick={() => onOpenGame(FORK_GAME)}>open fork game</button>
      <button onClick={() => onOpenGame(PLAIN_GAME)}>open plain game</button>
    </div>
  ),
}));
// Lets the test click a notation move by SAN path.
vi.mock('@/components/openings/GameViewerPanel', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/components/openings/GameViewerPanel')>();
  return {
    ...actual,
    default: (p: any) => {
      const nodes: any[] = [];
      const walk = (n: any) => { for (const c of n.children || []) { nodes.push(c); walk(c); } };
      if (p.editTree) walk(p.editTree);
      return (
        <div data-testid="game-viewer">
          {nodes.map(n => <button key={n.id} onClick={() => p.onEditNodeSelect?.(n)}>{`notation ${n.move_number}${n.is_white_move ? '.' : '…'}${n.move_san}`}</button>)}
        </div>
      );
    },
  };
});

import DebutPage from '../page';
import { pgnToTree } from '@/hooks/useGameMoveTree';

/** FEN reached by following `sans` from the start through the tree of `pgn`. */
function fenOf(pgn: string, sans: string[]): string {
  let n = pgnToTree(pgn);
  for (const san of sans) n = n.children!.find(c => c.move_san === san)!;
  return n.fen;
}

async function renderPage() {
  await act(async () => {
    render(<Suspense fallback={null}><DebutPage /></Suspense>);
  });
}

async function click(name: string) {
  // The viewer renders twice (phone + desktop layouts); either copy works.
  await act(async () => { fireEvent.click(screen.getAllByRole('button', { name })[0]); });
}

async function press(key: string) {
  let ev!: KeyboardEvent;
  await act(async () => {
    ev = new KeyboardEvent('keydown', { key, bubbles: true, cancelable: true });
    window.dispatchEvent(ev);
  });
  return ev;
}

const boardFen = () => screen.getByTestId('board').getAttribute('data-fen');
const nextBadge = () => screen.getByTestId('board').getAttribute('data-next-badge');
const pickers = () => screen.queryAllByTestId('fork-picker');

async function openGame(name: string) {
  await renderPage();
  await click('pick own db');
  await click(name);
}

beforeEach(() => {
  window.localStorage.clear();
  global.fetch = vi.fn(() => new Promise(() => {})) as unknown as typeof fetch;
  window.innerWidth = 1280;
});

afterEach(() => {
  cleanup();
  vi.restoreAllMocks();
});

describe('Database page — variation forks', () => {
  it('shows the picker, Next badge and numbered arrows only at a fork', async () => {
    await openGame('open fork game');
    expect(pickers()).toHaveLength(0);
    expect(nextBadge()).toBe('');
    await click('board next');
    expect(boardFen()).toBe(fenOf(FORK_PGN, ['e4']));
    expect(pickers().length).toBeGreaterThan(0);
    expect(nextBadge()).toBe('2');
    const arrows = JSON.parse(screen.getByTestId('board').getAttribute('data-arrows')!);
    expect(arrows.map((a: any) => [a.orig, a.dest, a.label.text])).toEqual([['e7', 'e5', '1'], ['c7', 'c5', '2']]);
  });

  it('Next at a fork plays the main line by default, then the branch entered from the picker', async () => {
    await openGame('open fork game');
    await click('board next');
    await click('board next');
    expect(boardFen()).toBe(fenOf(FORK_PGN, ['e4', 'e5']));

    await click('board prev');
    await act(async () => { fireEvent.click(screen.getAllByTestId('fork-option-2')[0]); });
    expect(boardFen()).toBe(fenOf(FORK_PGN, ['e4', 'c5']));

    // Back at the fork, Next follows the remembered branch; so does Go to end from the start.
    await click('board prev');
    await click('board next');
    expect(boardFen()).toBe(fenOf(FORK_PGN, ['e4', 'c5']));
    await click('board start');
    await click('board end');
    expect(boardFen()).toBe(fenOf(FORK_PGN, ['e4', 'c5', 'Nf3', 'd6']));
  });

  it('remembers a branch entered from the notation', async () => {
    await openGame('open fork game');
    // A move deep inside the 1…c5 line: the fork on its path remembers 1…c5.
    await click('notation 2…d6');
    await click('board start');
    await click('board next');
    await click('board next');
    expect(boardFen()).toBe(fenOf(FORK_PGN, ['e4', 'c5']));
  });

  it('↑/↓ move the highlight Next plays; number keys enter a continuation', async () => {
    await openGame('open fork game');
    await click('board next');
    expect((await press('ArrowDown')).defaultPrevented).toBe(true);
    expect(screen.getAllByTestId('fork-option-2')[0].getAttribute('aria-current')).toBe('true');
    const arrows = JSON.parse(screen.getByTestId('board').getAttribute('data-arrows')!);
    expect(arrows[1].brush).toBe('forkAltActive');
    await click('board next');
    expect(boardFen()).toBe(fenOf(FORK_PGN, ['e4', 'c5']));

    await click('board prev');
    await press('ArrowUp');
    await click('board next');
    expect(boardFen()).toBe(fenOf(FORK_PGN, ['e4', 'e5']));

    await click('board prev');
    await press('2');
    expect(boardFen()).toBe(fenOf(FORK_PGN, ['e4', 'c5']));
    // Out-of-range digits do nothing.
    await click('board prev');
    expect((await press('3')).defaultPrevented).toBe(false);
    expect(boardFen()).toBe(fenOf(FORK_PGN, ['e4']));
  });

  it('renders the picker once, under the board and above Stockfish, not in the notation', async () => {
    await openGame('open fork game');
    expect(screen.queryByTestId('board-fork-picker')).toBeNull();
    await click('board next');
    const slot = screen.getByTestId('board-fork-picker');
    expect(pickers()).toHaveLength(1);
    expect(slot.contains(pickers()[0])).toBe(true);
    for (const viewer of screen.getAllByTestId('game-viewer')) expect(viewer.contains(pickers()[0])).toBe(false);
    const board = screen.getByTestId('board');
    const engine = screen.getByRole('switch', { hidden: true });
    expect(board.compareDocumentPosition(slot) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
    expect(slot.compareDocumentPosition(engine) & Node.DOCUMENT_POSITION_FOLLOWING).toBeTruthy();
  });

  it('a game without forks navigates exactly as before', async () => {
    await openGame('open plain game');
    await click('board next');
    expect(boardFen()).toBe(fenOf(PLAIN_PGN, ['e4']));
    expect(pickers()).toHaveLength(0);
    expect(nextBadge()).toBe('');
    expect(screen.getByTestId('board').getAttribute('data-arrows')).toBe('[]');
    expect((await press('ArrowDown')).defaultPrevented).toBe(false);
    expect((await press('1')).defaultPrevented).toBe(false);
    expect(boardFen()).toBe(fenOf(PLAIN_PGN, ['e4']));
    await click('board end');
    expect(boardFen()).toBe(fenOf(PLAIN_PGN, ['e4', 'e5', 'Nf3']));
    await click('board prev');
    expect(boardFen()).toBe(fenOf(PLAIN_PGN, ['e4', 'e5']));
  });
});
