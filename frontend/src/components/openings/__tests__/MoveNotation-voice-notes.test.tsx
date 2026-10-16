// @vitest-environment jsdom
//
// Voice notes on moves: the 🔊 toggle next to noted moves (main line and
// variations, read-only too), the record flow (tap to record → tap to stop →
// preview → Save / Re-record / Cancel, auto-stop at 2:00, mic denied) from the
// action bar, desktop menu and mobile sheet, "Delete voice note", and the full
// round trip through useMoveVoiceNotes against a mocked API.
import { describe, it, expect, vi, afterEach, beforeEach } from 'vitest';
import { render, screen, fireEvent, cleanup, within, act, waitFor } from '@testing-library/react';
import React, { useState } from 'react';

vi.mock('@clerk/nextjs', () => ({ useAuth: () => ({ getToken: async () => 'clerk-token' }) }));
const apiFetch = vi.fn();
vi.mock('@/lib/api', () => ({
  apiFetch: (...args: unknown[]) => apiFetch(...args),
  ApiError: class extends Error {},
}));

import MoveNotation, { type MoveContextMenuActions, type VoiceNotePlayback } from '../MoveNotation';
import { pgnToTree, findNodeById } from '@/hooks/useGameMoveTree';
import { useMoveVoiceNotes } from '@/hooks/useMoveVoiceNotes';
import type { OpeningNode } from '@/types/openingNode';

// ─── Browser media mocks ─────────────────────────────────────────────────────

class FakeMediaRecorder {
  static isTypeSupported = (type: string) => type.startsWith('audio/webm');
  state: 'inactive' | 'recording' = 'inactive';
  mimeType: string;
  ondataavailable: ((e: { data: Blob }) => void) | null = null;
  onstop: (() => void) | null = null;
  constructor(_stream: unknown, opts: { mimeType: string }) {
    this.mimeType = opts.mimeType;
  }
  start() { this.state = 'recording'; }
  stop() {
    this.state = 'inactive';
    this.ondataavailable?.({ data: new Blob(['voice'], { type: this.mimeType }) });
    this.onstop?.();
  }
}

const getUserMedia = vi.fn();
const trackStop = vi.fn();

beforeEach(() => {
  apiFetch.mockReset();
  getUserMedia.mockReset();
  getUserMedia.mockResolvedValue({ getTracks: () => [{ stop: trackStop }] });
  (globalThis as unknown as { MediaRecorder: unknown }).MediaRecorder = FakeMediaRecorder;
  Object.defineProperty(navigator, 'mediaDevices', { configurable: true, value: { getUserMedia } });
  URL.createObjectURL = vi.fn(() => 'blob:preview');
  URL.revokeObjectURL = vi.fn();
});

afterEach(() => {
  cleanup();
  vi.useRealTimers();
  // @ts-expect-error — restore jsdom's default (no matchMedia)
  delete window.matchMedia;
});

function mockMatchMedia(matches: boolean) {
  Object.defineProperty(window, 'matchMedia', {
    configurable: true,
    writable: true,
    value: (query: string) => ({
      matches, media: query, onchange: null,
      addListener: () => {}, removeListener: () => {},
      addEventListener: () => {}, removeEventListener: () => {}, dispatchEvent: () => false,
    }),
  });
}

const LABELS: MoveContextMenuActions['labels'] = {
  voiceNote: 'Voice note',
  rerecordVoiceNote: 'Re-record voice note',
  deleteVoiceNote: 'Delete voice note',
  voice: 'Voice',
  deleteMove: 'Delete move',
  more: 'More',
  moreActions: 'More actions',
};

const PGN = '1. e4 e5 2. Nf3 (2. Bc4 Bc5) 2... Nc6';

function playback(paths: string[], overrides: Partial<VoiceNotePlayback> = {}): VoiceNotePlayback {
  return {
    paths: new Set(paths),
    playingPath: null,
    onToggle: vi.fn(),
    playLabel: 'Play voice note',
    pauseLabel: 'Pause voice note',
    ...overrides,
  };
}

function Notation({ actions, voiceNotes, select }: {
  actions?: MoveContextMenuActions;
  voiceNotes?: VoiceNotePlayback;
  select?: (t: OpeningNode) => string;
}) {
  const [tree] = useState(() => pgnToTree(PGN));
  const [selected, setSelected] = useState<string | null>(() => (select ? select(tree) : null));
  return (
    <MoveNotation
      tree={tree}
      selectedNodeId={selected}
      onNodeSelect={(n) => setSelected(n.id)}
      loading={false}
      contextMenuActions={actions}
      voiceNotes={voiceNotes}
    />
  );
}

const firstMove = (t: OpeningNode) => t.children![0].id;
const move = (san: string) => within(screen.getByTestId('move-notation-scroll')).getByText(san, { exact: true });

async function recordAndStop() {
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Record' })); });
  expect(screen.getByRole('button', { name: 'Stop' })).toBeTruthy();
  await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Stop' })); });
}

// ─── Playback ────────────────────────────────────────────────────────────────

describe('🔊 next to moves with a voice note', () => {
  it('renders for noted moves in the main line and in variations only', () => {
    render(<Notation voiceNotes={playback(['e4', 'e4 e5 Bc4 Bc5'])} />);
    const buttons = screen.getAllByTestId('move-voice-note');
    expect(buttons).toHaveLength(2);
    // Each 🔊 sits right after its move.
    expect(move('e4').nextElementSibling).toBe(buttons[0]);
    expect(move('Bc5').nextElementSibling).toBe(buttons[1]);
  });

  it('tap toggles play / pause for that move', () => {
    const onToggle = vi.fn();
    const { rerender } = render(<Notation voiceNotes={playback(['e4 e5'], { onToggle })} />);
    fireEvent.click(screen.getByRole('button', { name: 'Play voice note' }));
    expect(onToggle).toHaveBeenCalledWith('e4 e5');

    rerender(<Notation voiceNotes={playback(['e4 e5'], { onToggle, playingPath: 'e4 e5' })} />);
    const pause = screen.getByRole('button', { name: 'Pause voice note' });
    expect(pause.getAttribute('aria-pressed')).toBe('true');
  });

  it('read-only: plays, but offers no record or delete controls', () => {
    render(<Notation voiceNotes={playback(['e4'])} select={firstMove} />);
    expect(screen.getByTestId('move-voice-note')).toBeTruthy();
    expect(screen.queryByTestId('move-action-bar')).toBeNull();
    fireEvent.contextMenu(move('e4'));
    expect(screen.queryByRole('menu')).toBeNull();
    expect(screen.queryByText('Voice note')).toBeNull();
    expect(screen.queryByText('Delete voice note')).toBeNull();
  });
});

// ─── Recording ───────────────────────────────────────────────────────────────

describe('Recording a voice note', () => {
  it('desktop action bar: record → stop → preview → Save passes the recording', async () => {
    const onVoiceNoteSave = vi.fn().mockResolvedValue(true);
    render(<Notation actions={{ onVoiceNoteSave, labels: LABELS }} voiceNotes={playback([])} select={firstMove} />);

    fireEvent.click(within(screen.getByTestId('move-action-bar')).getByLabelText('Voice note'));
    const dialog = screen.getByRole('dialog');
    expect(within(dialog).getByText('1. e4')).toBeTruthy();

    await recordAndStop();
    expect(screen.getByTestId('voice-note-preview').getAttribute('src')).toBe('blob:preview');

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save' })); });
    expect(onVoiceNoteSave).toHaveBeenCalledTimes(1);
    const [node, recording] = onVoiceNoteSave.mock.calls[0];
    expect(node.move_san).toBe('e4');
    expect(recording.blob).toBeInstanceOf(Blob);
    expect(recording.blob.type).toBe('audio/webm;codecs=opus');
    expect(recording.durationMs).toBeGreaterThanOrEqual(0);
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(trackStop).toHaveBeenCalled();
  });

  it('shows a 2:00 limit and auto-stops there', async () => {
    vi.useFakeTimers();
    render(<Notation actions={{ onVoiceNoteSave: vi.fn(), labels: LABELS }} voiceNotes={playback([])} select={firstMove} />);
    fireEvent.click(within(screen.getByTestId('move-action-bar')).getByLabelText('Voice note'));
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Record' })); });
    expect(screen.getByRole('timer').textContent).toBe('0:00 / 2:00');

    await act(async () => { vi.advanceTimersByTime(65_000); });
    expect(screen.getByRole('timer').textContent).toBe('1:05 / 2:00');

    await act(async () => { vi.advanceTimersByTime(55_000); });
    expect(screen.getByTestId('voice-note-preview')).toBeTruthy();
    expect(screen.queryByRole('button', { name: 'Stop' })).toBeNull();
  });

  it('Re-record discards the take and records again; Cancel closes without saving', async () => {
    const onVoiceNoteSave = vi.fn();
    render(<Notation actions={{ onVoiceNoteSave, labels: LABELS }} voiceNotes={playback([])} select={firstMove} />);
    fireEvent.click(within(screen.getByTestId('move-action-bar')).getByLabelText('Voice note'));
    await recordAndStop();

    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Re-record' })); });
    expect(screen.queryByTestId('voice-note-preview')).toBeNull();
    expect(screen.getByRole('button', { name: 'Stop' })).toBeTruthy();
    expect(getUserMedia).toHaveBeenCalledTimes(2);

    fireEvent.click(screen.getByRole('button', { name: 'Cancel' }));
    await waitFor(() => expect(screen.queryByRole('dialog')).toBeNull());
    expect(onVoiceNoteSave).not.toHaveBeenCalled();
  });

  it('a failed save keeps the take and says so', async () => {
    const onVoiceNoteSave = vi.fn().mockResolvedValue(false);
    render(<Notation actions={{ onVoiceNoteSave, labels: LABELS }} voiceNotes={playback([])} select={firstMove} />);
    fireEvent.click(within(screen.getByTestId('move-action-bar')).getByLabelText('Voice note'));
    await recordAndStop();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save' })); });
    expect(screen.getByRole('alert').textContent).toMatch(/Couldn't save/);
    expect(screen.getByTestId('voice-note-preview')).toBeTruthy();
  });

  it('mic permission denied shows a clear message instead of crashing', async () => {
    getUserMedia.mockRejectedValue(Object.assign(new Error('denied'), { name: 'NotAllowedError' }));
    render(<Notation actions={{ onVoiceNoteSave: vi.fn(), labels: LABELS }} voiceNotes={playback([])} select={firstMove} />);
    fireEvent.click(within(screen.getByTestId('move-action-bar')).getByLabelText('Voice note'));
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Record' })); });
    expect(screen.getByRole('alert').textContent).toMatch(/Microphone access is blocked/);
    expect(screen.getByRole('button', { name: 'Record' })).toBeTruthy();
  });

  it('desktop right-click menu: "Voice note" opens the recorder', async () => {
    render(<Notation actions={{ onVoiceNoteSave: vi.fn(), labels: LABELS }} voiceNotes={playback([])} />);
    fireEvent.contextMenu(move('e5'));
    fireEvent.click(screen.getByRole('menuitem', { name: 'Voice note' }));
    const dialog = await screen.findByRole('dialog');
    expect(within(dialog).getByText('1… e5')).toBeTruthy();
    expect(within(dialog).getByTestId('voice-note-recorder')).toBeTruthy();
  });

  it('mobile: the action sheet and the fixed action bar open the recorder in the sheet', async () => {
    mockMatchMedia(true);
    render(<Notation actions={{ onVoiceNoteSave: vi.fn(), labels: LABELS }} voiceNotes={playback([])} select={firstMove} />);
    const bar = screen.getByTestId('move-action-bar');
    expect(within(bar).getByLabelText('Voice')).toBeTruthy();

    fireEvent.click(within(bar).getByLabelText('More'));
    fireEvent.click(within(screen.getByTestId('move-action-sheet')).getByText('Voice note'));
    expect(within(screen.getByTestId('move-action-sheet')).getByTestId('voice-note-recorder')).toBeTruthy();
  });
});

// ─── Delete ──────────────────────────────────────────────────────────────────

describe('Delete voice note', () => {
  it('is offered only for a move that has a note, which also reads "Re-record"', () => {
    const onVoiceNoteDelete = vi.fn();
    render(<Notation actions={{ onVoiceNoteSave: vi.fn(), onVoiceNoteDelete, labels: LABELS }} voiceNotes={playback(['e4'])} />);

    fireEvent.contextMenu(move('e5'));
    expect(screen.queryByRole('menuitem', { name: 'Delete voice note' })).toBeNull();
    fireEvent.keyDown(screen.getByRole('menu'), { key: 'Escape' });

    fireEvent.contextMenu(move('e4'));
    expect(screen.getByRole('menuitem', { name: 'Re-record voice note' })).toBeTruthy();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Delete voice note' }));
    expect(onVoiceNoteDelete).toHaveBeenCalledTimes(1);
    expect(onVoiceNoteDelete.mock.calls[0][0].move_san).toBe('e4');
  });
});

// ─── Round trip through useMoveVoiceNotes ────────────────────────────────────

function Wired({ gameId = 'game-1', shareToken }: { gameId?: string; shareToken?: string }) {
  const [tree] = useState(() => pgnToTree('1. e4 e5'));
  const [selected, setSelected] = useState<string | null>(() => tree.children![0].id);
  const notes = useMoveVoiceNotes({ gameId, shareToken });
  const pathOf = (n: OpeningNode) => {
    const parts: string[] = [];
    let cur: OpeningNode | null = n;
    while (cur?.move_san) {
      parts.unshift(cur.move_san);
      cur = cur.parent_id ? findNodeById(tree, cur.parent_id) : null;
    }
    return parts.join(' ');
  };
  return (
    <MoveNotation
      tree={tree}
      selectedNodeId={selected}
      onNodeSelect={(n) => setSelected(n.id)}
      loading={false}
      voiceNotes={{ paths: notes.paths, playingPath: notes.playingPath, onToggle: notes.toggle, playLabel: 'Play voice note', pauseLabel: 'Pause voice note' }}
      contextMenuActions={shareToken ? undefined : {
        onVoiceNoteSave: (n, rec) => notes.save(pathOf(n), rec),
        onVoiceNoteDelete: (n) => { notes.remove(pathOf(n)); },
        labels: LABELS,
      }}
    />
  );
}

describe('useMoveVoiceNotes round trip', () => {
  it('record → Save uploads to the game, then 🔊 shows; Delete calls the API and removes it', async () => {
    apiFetch.mockImplementation(async (url: string, opts: { method?: string } = {}) => {
      if (!opts.method) return [];
      if (opts.method === 'POST') return { id: 'note-1', node_path: 'e4', mime_type: 'audio/webm', duration_ms: 900, created_at: '' };
      return { success: true };
    });
    render(<Wired />);
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith('/api/games/game-1/voice-notes', expect.anything()));
    expect(screen.queryByTestId('move-voice-note')).toBeNull();

    fireEvent.click(within(screen.getByTestId('move-action-bar')).getByLabelText('Voice note'));
    await recordAndStop();
    await act(async () => { fireEvent.click(screen.getByRole('button', { name: 'Save' })); });

    const post = apiFetch.mock.calls.find(([, o]) => o?.method === 'POST')!;
    expect(post[0]).toBe('/api/games/game-1/voice-notes');
    expect(post[1].headers).toEqual({ Authorization: 'Bearer clerk-token' });
    const form = post[1].body as FormData;
    expect(form.get('node_path')).toBe('e4');
    expect(form.get('file')).toBeInstanceOf(Blob);
    expect(Number(form.get('duration_ms'))).toBeGreaterThanOrEqual(1);

    expect(await screen.findByTestId('move-voice-note')).toBeTruthy();
    expect(move('e4').nextElementSibling).toBe(screen.getByTestId('move-voice-note'));

    fireEvent.contextMenu(move('e4'));
    await act(async () => { fireEvent.click(screen.getByRole('menuitem', { name: 'Delete voice note' })); });
    const del = apiFetch.mock.calls.find(([, o]) => o?.method === 'DELETE')!;
    expect(del[0]).toBe('/api/games/game-1/voice-notes/note-1');
    await waitFor(() => expect(screen.queryByTestId('move-voice-note')).toBeNull());
  });

  it('a shared-database viewer lists and plays through the share token, with no record controls', async () => {
    const play = vi.fn().mockResolvedValue(undefined);
    const audios: string[] = [];
    vi.stubGlobal('Audio', class {
      onended: (() => void) | null = null;
      constructor(src: string) { audios.push(src); }
      play = play;
      pause = vi.fn();
    });
    apiFetch.mockImplementation(async (url: string) => (
      url.endsWith('/url?share_token=tok')
        ? { url: 'https://signed.example/a.webm' }
        : [{ id: 'note-9', node_path: 'e4 e5', mime_type: 'audio/webm', duration_ms: 900, created_at: '' }]
    ));
    render(<Wired shareToken="tok" />);
    await waitFor(() => expect(apiFetch).toHaveBeenCalledWith('/api/games/game-1/voice-notes?share_token=tok', expect.anything()));
    const speaker = await screen.findByRole('button', { name: 'Play voice note' });
    expect(screen.queryByTestId('move-action-bar')).toBeNull();

    await act(async () => { fireEvent.click(speaker); });
    expect(apiFetch).toHaveBeenCalledWith('/api/games/game-1/voice-notes/note-9/url?share_token=tok', expect.anything());
    expect(audios).toEqual(['https://signed.example/a.webm']);
    expect(play).toHaveBeenCalled();
    expect(screen.getByRole('button', { name: 'Pause voice note' })).toBeTruthy();
    vi.unstubAllGlobals();
  });
});
