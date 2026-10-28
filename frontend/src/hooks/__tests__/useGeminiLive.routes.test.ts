/**
 * @vitest-environment jsdom
 */
/**
 * The voice seam, driven end to end (28.10): the REAL useGeminiLive hook, its fetch routed into the
 * REAL Next route handlers, only Hermes (HERMES_URL) stubbed. What reaches Hermes is checked against
 * Hermes's request models (hermes_contract.json): every field the hook sends and Hermes reads arrives,
 * nothing Hermes does not declare reaches it, nothing the hook sends is read by nobody.
 *
 * Why: seam.contract.test.ts feeds the routes bodies copied by hand from the hook; a body the hook
 * changes later is not what it checks. Here the body is whatever the hook builds today.
 * Both historic drops (engine-note forwarding only { fen }, idea dropping pgn) fail these tests.
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';
import { CLEAN, createHarness, defaultHermesReply as defaultReply, hermesBody, seamProblems, HERMES, type Harness } from '@/app/api/coach/__tests__/seam-harness';

// ---- server side: as the route tests mock it ----------------------------------
vi.mock('next/server', async (orig) => ({ ...(await orig<typeof import('next/server')>()), after: () => {} }));
vi.mock('@clerk/nextjs/server', () => ({ auth: async () => ({ userId: 'u1' }) }));
vi.mock('@/lib/coach-access', () => ({ requireCoachAccess: async () => null }));
vi.mock('@/lib/require-api-access', () => ({ requireApiAccess: async () => null }));
vi.mock('@/lib/subscription-tier', () => ({ resolveUserTier: async () => 'pro' }));
vi.mock('@/lib/analytics/server', () => ({ captureServer: () => {} }));
vi.mock('@/lib/analytics/events', async (orig) => ({ ...(await orig<typeof import('@/lib/analytics/events')>()), track: () => {} }));

// ---- @google/genai: the route mints a token, the hook opens a Live session ----
const g = vi.hoisted(() => ({
  session: { sendRealtimeInput: vi.fn(), sendClientContent: vi.fn(), sendToolResponse: vi.fn(), close: vi.fn() },
  callbacks: null as null | { onmessage: (m: unknown) => void },
}));
vi.mock('@google/genai', () => ({
  GoogleGenAI: class {
    authTokens = { create: async () => ({ name: 'auth_tokens/test' }) };
    live = {
      connect: async (params: { callbacks: { onmessage: (m: unknown) => void } }) => {
        g.callbacks = params.callbacks;
        return g.session;
      },
    };
  },
  Modality: { AUDIO: 'AUDIO' }, EndSensitivity: { END_SENSITIVITY_HIGH: 'H' }, Behavior: { BLOCKING: 'B' },
}));

// Routes read HERMES_URL when first imported, which the harness does lazily inside the tests.
vi.stubEnv('HERMES_URL', HERMES);
vi.stubEnv('GEMINI_API_KEY', 'test-not-a-key');

import useGeminiLive from '../useGeminiLive';

// ---- browser audio fakes (the hook needs a mic and two AudioContexts) ----------
class FakeAudioContext {
  destination = {};
  currentTime = 0;
  sampleRate = 48000;
  state = 'running';
  audioWorklet = { addModule: async () => {} };
  resume = async () => {};
  close = async () => {};
  createMediaStreamSource = () => ({ connect: () => {} });
  createBuffer = (_c: number, len: number, rate: number) => ({ duration: len / rate, getChannelData: () => new Float32Array(len) });
  createBufferSource = () => ({ buffer: null, connect: () => {}, start: () => {}, stop: () => {}, onended: null });
}
class FakeAudioWorkletNode {
  port = { onmessage: null, postMessage: () => {} };
  connect = () => {};
  disconnect = () => {};
}

const START = 'rnbqkbnr/pppppppp/8/8/8/8/PPPPPPPP/RNBQKBNR w KQkq - 0 1';
const AFTER = 'rnbqkbnr/ppp1pppp/8/3p4/4P3/8/PPPP1PPP/RNBQKBNR w KQkq d6 0 2';
const PGN = '1. e4 e5 2. Nf3';
const game = (over: Record<string, unknown> = {}) => ({
  board_id: 'b1', student_color: 'white', engine_elo: 1200, comment_mode: 'quiet', status: 'playing',
  result: null, termination: null, winner: null, fen: START, pgn: '', ply: 0, moves: [],
  student_to_move: true, in_check: false, student: null, engine: null, comment_wanted: false, ...over,
});
const AFTER_GAME = game({ fen: AFTER, student: { san: 'e4', uci: 'e2e4', verdict: 'ok', cp_loss: 0, eval_after: 0.3, best: null }, engine: { san: 'd5', uci: 'd7d5' } });

let h: Harness;

beforeEach(() => {
  Object.values(g.session).forEach((f) => f.mockReset());
  g.callbacks = null;
  vi.stubGlobal('AudioContext', FakeAudioContext);
  vi.stubGlobal('AudioWorkletNode', FakeAudioWorkletNode);
  Object.defineProperty(navigator, 'mediaDevices', {
    configurable: true,
    value: { getUserMedia: async () => ({ getTracks: () => [{ stop: () => {} }] }) },
  });
  h = createHarness();
  vi.stubGlobal('fetch', vi.fn(h.fetch));
});

afterEach(async () => {
  // Every call the hook made in the test went through its seam clean, not only the one asserted.
  await h.settled();
  expect(h.problems()).toEqual({});
  vi.unstubAllGlobals();
});

async function connectWith(opts: Record<string, unknown>) {
  const hook = renderHook(() => useGeminiLive(opts as never));
  await act(async () => {
    await hook.result.current.connect();
  });
  expect(hook.result.current.isActive).toBe(true);
  return hook;
}
const say = (text: string) => act(() => g.callbacks!.onmessage({ serverContent: { inputTranscription: { text } } }));
const coachSays = (text: string) => act(() => g.callbacks!.onmessage({ serverContent: { outputTranscription: { text } } }));
const modelCalls = async (name: string, args: Record<string, unknown>) => {
  await act(async () => {
    g.callbacks!.onmessage({ toolCall: { functionCalls: [{ id: 'c1', name, args }] } });
    await new Promise((r) => setTimeout(r, 0));
  });
};
/** The one Hermes body a site call produced. */
const atHermes = (path: string, i = -1) => {
  const call = h.to(path).at(i);
  expect(call, `the hook never called ${path}`).toBeDefined();
  expect(seamProblems(call!)).toEqual(CLEAN);
  return { sent: call!.sent, hermes: hermesBody(call!) };
};
const toolCalls = (name: string) => h.to('/api/coach/tool').filter((c) => c.sent.name === name);

describe('voice seam through the real proxies: what the hook sends and Hermes reads reaches Hermes', () => {
  it('live-token -> voice/prompt: the position and the session the voice continues', async () => {
    await connectWith({ getFen: () => START, getSessionId: () => 's1' });
    expect(atHermes('/api/coach/live-token', 0)).toMatchObject({ sent: { fen: START, session_id: 's1' }, hermes: { fen: START, session_id: 's1' } });
  });

  it('engine-note outside a game: the position, with the session', async () => {
    await connectWith({ getFen: () => START, getSessionId: () => 's1' });
    await waitFor(() => expect(h.to('/api/coach/voice/engine-note')).toHaveLength(1));
    expect(atHermes('/api/coach/voice/engine-note')).toMatchObject({ sent: { fen: START, session_id: 's1' }, hermes: { fen: START, session_id: 's1' } });
  });

  it('engine-note in a game: the session reaches Hermes, so it answers with the game facts and no best move', async () => {
    let current = game();
    const { result } = await connectWith({ getGame: () => current, getSessionId: () => 's1' });
    current = AFTER_GAME;
    act(() => result.current.sendBoardUpdate(AFTER));
    await waitFor(() => expect(h.to('/api/coach/voice/engine-note').some((c) => c.sent.fen === AFTER)).toBe(true));
    expect(atHermes('/api/coach/voice/engine-note')).toMatchObject({ sent: { fen: AFTER, session_id: 's1' }, hermes: { fen: AFTER, session_id: 's1' } });
  });

  it('idea outside a game: the game on the board (pgn) reaches Hermes, for «на 8-м ходу»', async () => {
    await connectWith({ getFen: () => START, getPgn: () => PGN, getSessionId: () => 's1' });
    say('а если Кf3');
    await waitFor(() => expect(h.to('/api/coach/voice/idea')).toHaveLength(1));
    expect(atHermes('/api/coach/voice/idea')).toMatchObject({
      sent: { text: 'а если Кf3', fen: START, pgn: PGN },
      hermes: { text: 'а если Кf3', fen: START, pgn: PGN, live_game: false },
    });
  });

  it('idea in a game: live_game reaches Hermes (a «what if», never the engine\'s move)', async () => {
    h.reply = (path, body) => (path === '/api/coach/voice/intent' ? { kind: 'idea' } : defaultReply(path));
    await connectWith({ getGame: () => game(), getFen: () => START, getSessionId: () => 's1' });
    say('а что если слон на c4');
    await waitFor(() => expect(h.to('/api/coach/voice/idea')).toHaveLength(1));
    expect(atHermes('/api/coach/voice/idea')).toMatchObject({
      sent: { text: 'а что если слон на c4', fen: START, live_game: true },
      hermes: { text: 'а что если слон на c4', fen: START, live_game: true },
    });
  });

  it('intent: the words with the session, the position and the game on the board', async () => {
    await connectWith({ getFen: () => START, getPgn: () => PGN, getSessionId: () => 's1' });
    say('разбери мою партию');
    await waitFor(() => expect(h.to('/api/coach/voice/intent')).toHaveLength(1));
    expect(atHermes('/api/coach/voice/intent')).toMatchObject({
      sent: { text: 'разбери мою партию', session_id: 's1', fen: START, pgn: PGN },
      hermes: { text: 'разбери мою партию', session_id: 's1', fen: START, pgn: PGN },
    });
  });

  it('check outside a game: the coach\'s sentence with the game on the board (pgn) and the session', async () => {
    const pgn = '1. e4 e5 2. Nf3 Nc6 3. Bc4 Bc5';
    await connectWith({ getGame: () => null, getFen: () => START, getPgn: () => pgn, getSessionId: () => 's1' });
    coachSays('Партия шла так: 1. e4 e5 2. Кf3 Кc6 3. Сc4 Сc5. ');
    await waitFor(() => expect(h.to('/api/coach/voice/check')).toHaveLength(1));
    expect(atHermes('/api/coach/voice/check')).toMatchObject({ sent: { fen: START, pgn, session_id: 's1' }, hermes: { fen: START, pgn, session_id: 's1' } });
  });

  it('check in a game: the session, so Hermes reads the spoken move against the game', async () => {
    await connectWith({ getGame: () => game(), getFen: () => START, getSessionId: () => 's1' });
    coachSays('Хорошо. Я пойду конём на d3. ');
    await waitFor(() => expect(h.to('/api/coach/voice/check')).toHaveLength(1));
    expect(atHermes('/api/coach/voice/check')).toMatchObject({ sent: { fen: START, session_id: 's1' }, hermes: { fen: START, session_id: 's1' } });
  });

  it('tool make_game_move called by the model: args, session and the student\'s words reach Hermes', async () => {
    h.reply = (path, body) => (path === '/api/coach/tool/make_game_move'
      ? { result: { ok: true, student_move: 'e4', engine_reply: 'd5' }, board_actions: [{ type: 'game', game: AFTER_GAME }] }
      : defaultReply(path));
    await connectWith({ getGame: () => game(), getFen: () => START, getSessionId: () => 's1' });
    say('Как здесь лучше?');
    await modelCalls('make_game_move', { move: 'e4' });
    await waitFor(() => expect(toolCalls('make_game_move')).toHaveLength(1));
    const call = toolCalls('make_game_move')[0];
    expect(seamProblems(call)).toEqual(CLEAN);
    expect(call.hermes[0]).toMatchObject({
      path: '/api/coach/tool/make_game_move',
      body: { args: { move: 'e4' }, session_id: 's1', utterance: 'Как здесь лучше?' },
    });
  });

  it('tool make_game_move played by the site for a move Hermes read from the words', async () => {
    h.reply = (path, body) => {
      if (path === '/api/coach/voice/intent') return { kind: 'move', san: 'Bc4' };
      if (path === '/api/coach/tool/make_game_move') return { result: { ok: true, student_move: 'Bc4', engine_reply: 'Nf6' }, board_actions: [{ type: 'game', game: AFTER_GAME }] };
      return defaultReply(path);
    };
    await connectWith({ getGame: () => game(), getFen: () => START, getSessionId: () => 's1' });
    say('слон си четыре');
    await waitFor(() => expect(toolCalls('make_game_move')).toHaveLength(1));
    expect(toolCalls('make_game_move')[0].hermes[0].body).toMatchObject({ args: { move: 'Bc4' }, session_id: 's1', utterance: 'слон си четыре' });
  });

  it('tool game_action: the correction goes to the game as the words', async () => {
    h.reply = (path, body) => {
      if (path === '/api/coach/voice/intent') return { kind: 'game_command', command: 'correct' };
      if (path === '/api/coach/tool/game_action') return { result: { ok: true, action: 'correct', done: true, note: 'c6 is played instead.' }, board_actions: [{ type: 'game', game: AFTER_GAME }] };
      return defaultReply(path);
    };
    await connectWith({ getGame: () => game(), getFen: () => START, getSessionId: () => 's1' });
    say('Не конь, а пешка на c6');
    await waitFor(() => expect(toolCalls('game_action')).toHaveLength(1));
    const call = toolCalls('game_action')[0];
    expect(seamProblems(call)).toEqual(CLEAN);
    expect(call.hermes[0]).toMatchObject({
      path: '/api/coach/tool/game_action',
      body: { args: { said: 'Не конь, а пешка на c6' }, session_id: 's1', utterance: 'Не конь, а пешка на c6' },
    });
  });

  it('regression: the engine-note proxy before 47ad04f1 (fen only) fails the in-game path', async () => {
    h.overrides['voice/engine-note'] = await import('@/app/api/coach/__tests__/fixtures/engine-note-route.before-47ad04f1');
    let current = game();
    const { result } = await connectWith({ getGame: () => current, getSessionId: () => 's1' });
    current = AFTER_GAME;
    act(() => result.current.sendBoardUpdate(AFTER));
    await waitFor(() => expect(h.to('/api/coach/voice/engine-note').some((c) => c.sent.fen === AFTER)).toBe(true));
    const notes = h.to('/api/coach/voice/engine-note');
    expect(seamProblems(notes.at(-1)!)).toEqual({ ...CLEAN, dropped: ['session_id'] });
    // Leave the clean-seam check in afterEach to the real routes.
    h.calls.splice(0, h.calls.length, ...h.calls.filter((c) => c.path !== '/api/coach/voice/engine-note'));
  });
});

