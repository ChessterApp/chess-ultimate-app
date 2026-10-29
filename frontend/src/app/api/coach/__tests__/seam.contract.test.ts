/**
 * The site -> Hermes seam (28.10). Each row is one place where the page calls a coach proxy:
 * the body the page really sends (file:line in `client`), fed to the REAL route handler, with
 * only fetch to HERMES_URL stubbed. What reaches Hermes is checked against Hermes's request
 * model (hermes_contract.json, generated from hermes/src by hermes/scripts/hermes_contract.py;
 * hermes/tests/unit/test_hermes_contract_fresh.py fails when it is stale).
 *
 * Why: engine-note's proxy forwarded only { fen } for two weeks; the hook's test checked the body
 * before the proxy and Hermes's test posted the stripped body itself, so both stayed green.
 *
 * Per row, all must hold:
 *  - dropped: a field the page sends and Hermes reads arrives unchanged;
 *  - unknown: nothing reaches Hermes that its model does not declare (pydantic would drop it silently);
 *  - orphan:  every field the page sends is read by Hermes or by the proxy itself (`proxyReads`);
 *  - unsent:  Hermes fields nobody fills are exactly the documented `hermesOnly` ones.
 * And both sides are covered: every body-carrying coach route and every Hermes body endpoint is a
 * row or is listed below with the reason it is not.
 *
 * Changing a proxy, the page's body or a Hermes model: update the row (and regenerate the JSON).
 * The voice hook and the chat page are also run as they are, through these routes (no copied bodies):
 * hooks/__tests__/useGeminiLive.routes.test.ts, components/coach/__tests__/CoachChat.routes.test.tsx.
 */
import { readdirSync, readFileSync } from 'node:fs';
import { dirname, join, relative } from 'node:path';
import { fileURLToPath } from 'node:url';
import { describe, it, expect, vi, afterEach } from 'vitest';
import contractJson from './hermes_contract.json';

vi.mock('next/server', async (orig) => ({ ...(await orig<typeof import('next/server')>()), after: () => {} }));
vi.mock('@clerk/nextjs/server', () => ({ auth: async () => ({ userId: 'u1' }) }));
vi.mock('@/lib/coach-access', () => ({ requireCoachAccess: async () => null }));
vi.mock('@/lib/require-api-access', () => ({ requireApiAccess: async () => null }));
vi.mock('@/lib/subscription-tier', () => ({ resolveUserTier: async () => 'pro' }));
vi.mock('@/lib/analytics/server', () => ({ captureServer: () => {} }));
vi.mock('@google/genai', () => ({
  GoogleGenAI: class { authTokens = { create: async () => ({ name: 'tok' }) }; },
  Modality: { AUDIO: 'AUDIO' }, EndSensitivity: { END_SENSITIVITY_HIGH: 'H' }, Behavior: { BLOCKING: 'B' },
}));

// Routes read HERMES_URL when first imported, which happens inside the tests below.
const HERMES = 'http://hermes.test';
vi.stubEnv('HERMES_URL', HERMES);
vi.stubEnv('GEMINI_API_KEY', 'test-not-a-key');

type Contract = Record<string, { model: string | null; fields: string[] | null }>;
const CONTRACT = contractJson as Contract;
const FEN = 'rnbqkbnr/pppp1ppp/8/4p3/4P3/5N2/PPPP1PPP/RNBQKB1R b KQkq - 1 2';
const PGN = '1. e4 e5 2. Nf3';
type Method = 'POST' | 'PUT' | 'PATCH';

type Row = {
  name: string;
  /** The site route under app/api/coach (folder of its route.ts). */
  route: string;
  method: Method;
  /** Where the page builds this body (paths under frontend/src). */
  client: string;
  /** What the page sends; undefined = no body at all. */
  body?: Record<string, unknown>;
  params?: Record<string, string>;
  /** Contract key: Hermes's METHOD + path template. */
  hermes: string;
  hermesUrl: RegExp;
  cookie?: string;
  /** Body fields the proxy itself consumes and Hermes need not get, with why. */
  proxyReads?: Record<string, string>;
  /** Hermes fields this caller leaves empty on purpose (or a known gap), with why. */
  hermesOnly?: Record<string, string>;
};

const rows: Row[] = [
  { name: 'voice/engine-note (voice coach)', route: 'voice/engine-note', method: 'POST', client: 'hooks/useGeminiLive.ts:2179-2185',
    body: { fen: FEN, session_id: 's1' }, hermes: 'POST /api/coach/voice/engine-note', hermesUrl: /\/api\/coach\/voice\/engine-note$/ },
  { name: 'voice/engine-note (text page prewarm)', route: 'voice/engine-note', method: 'POST', client: 'lib/coach/boards-api.ts:275-281',
    body: { fen: FEN }, hermes: 'POST /api/coach/voice/engine-note', hermesUrl: /\/api\/coach\/voice\/engine-note$/,
    hermesOnly: { session_id: 'the prewarm only fills the engine cache for the position; its note is never read' } },
  { name: 'voice/idea (not in a game)', route: 'voice/idea', method: 'POST', client: 'hooks/useGeminiLive.ts:1775-1783',
    body: { text: 'а что если на 2-м ходу Кc6?', fen: FEN, pgn: PGN }, hermes: 'POST /api/coach/voice/idea', hermesUrl: /\/api\/coach\/voice\/idea$/ },
  { name: 'voice/idea (live game)', route: 'voice/idea', method: 'POST', client: 'hooks/useGeminiLive.ts:1775-1782',
    body: { text: 'а если Кc6?', fen: FEN, live_game: true }, hermes: 'POST /api/coach/voice/idea', hermesUrl: /\/api\/coach\/voice\/idea$/,
    hermesOnly: { pgn: 'in a live game the idea is a «what if» on the current position, no past move to find' } },
  { name: 'voice/check (not in a game)', route: 'voice/check', method: 'POST', client: 'hooks/useGeminiLive.ts:1342-1356',
    body: { text: 'Партия шла так: 1. e4 e5', fen: FEN, pgn: PGN, question: 'как шла партия?', session_id: 's1' },
    hermes: 'POST /api/coach/voice/check', hermesUrl: /\/api\/coach\/voice\/check$/ },
  { name: 'voice/check (live game)', route: 'voice/check', method: 'POST', client: 'hooks/useGeminiLive.ts:1342-1356',
    body: { text: 'Мой ответ — конь на f6', fen: FEN, question: 'что ты играешь?', session_id: 's1' },
    hermes: 'POST /api/coach/voice/check', hermesUrl: /\/api\/coach\/voice\/check$/,
    hermesOnly: { pgn: 'in a live game Hermes reads the game from the session (28.10)' } },
  { name: 'voice/intent', route: 'voice/intent', method: 'POST', client: 'hooks/useGeminiLive.ts:1586-1595',
    body: { text: 'разбери мою партию', session_id: 's1', fen: FEN, pgn: PGN }, hermes: 'POST /api/coach/voice/intent', hermesUrl: /\/api\/coach\/voice\/intent$/ },
  { name: 'voice/tts', route: 'voice/tts', method: 'POST', client: 'hooks/usePipelineVoice.ts:236-240',
    body: { text: 'Сейчас посмотрю.', locale: 'ru' }, hermes: 'POST /api/coach/voice/tts', hermesUrl: /\/api\/coach\/voice\/tts$/ },
  { name: 'tool', route: 'tool', method: 'POST', client: 'hooks/useGeminiLive.ts:1172-1183 (also :1488, :1554, :1616)',
    body: { name: 'board_control', args: { action_type: 'set_fen' }, session_id: 's1', utterance: 'поставь позицию', caller: 'site' },
    hermes: 'POST /api/coach/tool/{name}', hermesUrl: /\/api\/coach\/tool\/board_control$/,
    proxyReads: { name: 'goes into the Hermes path /tool/{name}' } },
  { name: 'chat', route: 'chat', method: 'POST', client: 'components/coach/CoachChat.tsx:811-832', cookie: 'NEXT_LOCALE=ru',
    body: { message: 'что тут играть?', context_note: '[Review context]', fen: FEN, session_id: 's1', board_id: 'b1', review_game_id: 'g1', speech: true, view_ply: 3, view_line: ['e4', 'e5', 'Nf3'] },
    hermes: 'POST /api/coach/chat', hermesUrl: /\/api\/coach\/chat$/ },
  { name: 'live-token -> voice/prompt', route: 'live-token', method: 'POST', client: 'hooks/useGeminiLive.ts:2219-2230', cookie: 'NEXT_LOCALE=ru',
    body: { fen: FEN, session_id: 's1', resume: 'h1' }, hermes: 'POST /api/coach/voice/prompt', hermesUrl: /\/api\/coach\/voice\/prompt$/,
    proxyReads: { resume: 'read by nobody server-side: the hook resumes the Live session itself (useGeminiLive.ts:2325-2326)' } },
  { name: 'voice-usage -> heartbeat', route: 'voice-usage', method: 'POST', client: 'hooks/useGeminiLive.ts:816-824',
    body: { session_id: 's1', seconds_delta: 15 }, hermes: 'POST /internal/voice/heartbeat', hermesUrl: /\/internal\/voice\/heartbeat$/ },
  { name: 'sessions/[id]/messages', route: 'sessions/[id]/messages', method: 'POST', client: 'components/coach/CoachChat.tsx:357-368', params: { id: 's1' },
    body: { role: 'assistant', content: 'реплика', source: 'voice', client_ts: '2026-10-28T00:00:00Z', turn_id: 't1' },
    hermes: 'POST /api/coach/sessions/{session_id}/messages', hermesUrl: /\/api\/coach\/sessions\/s1\/messages$/ },
  { name: 'feedback', route: 'feedback', method: 'POST', client: 'components/coach/FeedbackButtons.tsx:38-47',
    body: { turn_id: 't1', session_id: 's1', rating: 1, surface: 'voice', comment: 'ok' }, hermes: 'POST /api/coach/feedback', hermesUrl: /\/api\/coach\/feedback$/,
    hermesOnly: { client_ts: 'the buttons send none; Hermes records its own time' } },
  { name: 'import-url', route: 'import-url', method: 'POST', client: 'components/coach/CoachChat.tsx:642-645',
    body: { url: 'https://lichess.org/abcdefgh' }, hermes: 'POST /api/coach/import-url', hermesUrl: /\/api\/coach\/import-url$/ },
  { name: 'sessions (create)', route: 'sessions', method: 'POST', client: 'lib/coach/boards-api.ts:170-171 (CoachChat.tsx:536 sends {})',
    body: { title: 'Новая' }, hermes: 'POST /api/coach/sessions', hermesUrl: /\/api\/coach\/sessions$/ },
  { name: 'sessions/[id] (update)', route: 'sessions/[id]', method: 'PATCH', client: 'lib/coach/boards-api.ts:173-177', params: { id: 's1' },
    body: { title: 'x', active_board_id: 'b1' }, hermes: 'PATCH /api/coach/sessions/{session_id}', hermesUrl: /\/api\/coach\/sessions\/s1$/ },
  { name: 'boards (create)', route: 'sessions/[id]/boards', method: 'POST', client: 'lib/coach/boards-api.ts:186-203', params: { id: 's1' },
    body: { kind: 'game', title: 't', pgn: PGN, fen: FEN, ply: 3, orientation: 'black', source: { k: 1 }, activate: true },
    hermes: 'POST /api/coach/sessions/{session_id}/boards', hermesUrl: /\/api\/coach\/sessions\/s1\/boards$/ },
  { name: 'boards/[boardId] (update)', route: 'sessions/[id]/boards/[boardId]', method: 'PATCH', client: 'lib/coach/boards-api.ts:205-222', params: { id: 's1', boardId: 'b1' },
    body: { title: 't', pgn: PGN, fen: FEN, position: FEN, ply: 3, orientation: 'white', annotations: { arrows: [] }, active: true },
    hermes: 'PATCH /api/coach/sessions/{session_id}/boards/{board_id}', hermesUrl: /\/api\/coach\/sessions\/s1\/boards\/b1$/,
    hermesOnly: { game_state: 'the page only reads it (coach/page.tsx:59); the game endpoints write it' } },
  { name: 'game (start)', route: 'sessions/[id]/game', method: 'POST', client: 'lib/coach/boards-api.ts:231-235', params: { id: 's1' },
    body: { color: 'black', elo: 1200, comment_mode: 'every' }, hermes: 'POST /api/coach/sessions/{session_id}/game', hermesUrl: /\/api\/coach\/sessions\/s1\/game$/ },
  ...(
    [
      ['move', 'lib/coach/boards-api.ts:237-241', { move: 'e5' }],
      ['resign', 'lib/coach/boards-api.ts:243-247', undefined],
      ['takeback', 'lib/coach/boards-api.ts:249-253', undefined],
      ['continue', 'lib/coach/boards-api.ts:256-260', { ply: 3, line: ['e4', 'e5', 'Nf3'] }],
      ['comment', 'app/coach/page.tsx:606-612 (CoachChat.tsx streamAssistant)', { event: 'move', speech: true }],
    ] as const
  ).map(([action, client, body]): Row => ({
    name: `game ${action}`, route: 'sessions/[id]/game/[boardId]/[action]', method: 'POST', client, body, cookie: 'NEXT_LOCALE=ru',
    params: { id: 's1', boardId: 'b1', action },
    hermes: `POST /api/coach/sessions/{session_id}/game/{board_id}/${action}`, hermesUrl: new RegExp(`/game/b1/${action}$`),
  })),
];

/**
 * Fields the page sends that the proxy drops, and how long that has been known. The row's test
 * pins the exact drop; when the fix lands it turns red: delete the entry so the row is a plain check.
 */
const KNOWN_DROPS: Record<string, { dropped: string[]; note: string }> = {
  // none: voice/idea's pgn (lost since 12.10) is forwarded since 28.10
};

/** Site route + method pairs with a body that are not rows, and why. */
const SITE_NOT_ROWS: Record<string, string> = {
  'analysis POST': 'Hermes reads a raw dict (no request model), so there is no field list to check',
  'analysis/stream POST': 'Hermes reads a raw dict (no request model)',
  'metrics POST': 'passes the body through whole; Hermes reads a raw dict',
  'profile PUT': 'passes the body through whole; Hermes reads a raw dict',
  'review-cache POST': 'does not call Hermes',
};

/** Hermes body endpoints with no row, and why. */
const HERMES_NOT_ROWS: Record<string, string> = {
  'POST /v1/chat/completions': 'OpenAI-compatible endpoint, no site proxy',
  'POST /api/lesson/chat': 'the /learn lesson tutor (api/tutor/**), the team\'s feature, kept out of this contract',
  'POST /api/coach/analysis': 'raw dict, see SITE_NOT_ROWS',
  'POST /api/coach/analysis/stream': 'raw dict, see SITE_NOT_ROWS',
  'POST /api/coach/metrics': 'raw dict, see SITE_NOT_ROWS',
  'PUT /api/coach/profile': 'raw dict, see SITE_NOT_ROWS',
  'POST /api/coach/create-checkout-session': 'no site caller',
  'POST /api/coach/whop-webhook': 'called by Whop, not by the site',
};

type Problems = { dropped: string[]; unknown: string[]; orphan: string[]; unsent: string[] };
const CLEAN: Problems = { dropped: [], unknown: [], orphan: [], unsent: [] };

/** What is wrong with `sent` (the JSON that reached Hermes) for this row. */
function seamProblems(row: Row, sent: Record<string, unknown>): Problems {
  const declared = CONTRACT[row.hermes].fields ?? [];  // null: Hermes reads no body
  const body = row.body ?? {};
  const present = Object.keys(sent).filter((k) => sent[k] !== undefined);
  // Hermes fields nobody fills; one the page sends is already reported as dropped.
  const empty = declared.filter((k) => !present.includes(k) && !(k in body));
  const documented = Object.keys(row.hermesOnly ?? {});
  return {
    dropped: Object.keys(body).filter((k) => declared.includes(k) && JSON.stringify(sent[k]) !== JSON.stringify(body[k])),
    unknown: present.filter((k) => !declared.includes(k)),
    orphan: Object.keys(body).filter((k) => !declared.includes(k) && !(row.proxyReads && k in row.proxyReads)),
    unsent: [
      ...empty.filter((k) => !documented.includes(k)),
      // A documented gap that is now filled (or gone from Hermes) must leave the table too.
      ...documented.filter((k) => !empty.includes(k)).map((k) => `stale hermesOnly: ${k}`),
    ],
  };
}

const okJson = (data: unknown = {}) => new Response(JSON.stringify(data), { status: 200, headers: { 'content-type': 'application/json' } });

type Handler = (req: unknown, ctx: { params: Promise<Record<string, string>> }) => Promise<Response>;

/** Run the route handler on the page's body; return the JSON body of its request to `row.hermesUrl`. */
async function sentToHermes(row: Row, mod: Record<string, unknown>): Promise<Record<string, unknown>> {
  const fetchMock = vi.fn(async (url: unknown) => {
    const u = String(url);
    // Only Hermes is stubbed: any other host means a route reached somewhere the test does not know.
    if (!u.startsWith(HERMES)) throw new Error(`unexpected fetch outside HERMES_URL: ${u}`);
    return okJson(u.includes('/api/coach/tools') ? { tools: [] } : { messages: [] });
  });
  vi.stubGlobal('fetch', fetchMock);
  const { NextRequest } = await import('next/server');
  const req = new NextRequest('http://localhost/api/coach/x', {
    method: row.method,
    headers: { 'content-type': 'application/json', ...(row.cookie ? { cookie: row.cookie } : {}) },
    body: row.body === undefined ? undefined : JSON.stringify(row.body),
  });
  const handler = mod[row.method] as Handler | undefined;
  expect(handler, `${row.route} exports no ${row.method}`).toBeTypeOf('function');
  const res = await handler!(req, { params: Promise.resolve(row.params ?? {}) });
  await res.text();  // streaming proxies call Hermes inside the stream
  const calls = fetchMock.mock.calls.filter(([u]) => row.hermesUrl.test(String(u).split('?')[0]));
  expect(calls, `no request to Hermes ${row.hermes} (status ${res.status})`).toHaveLength(1);
  const init = (calls[0] as unknown[])[1] as RequestInit | undefined;
  return typeof init?.body === 'string' && init.body ? JSON.parse(init.body) : {};
}

const loadRoute = (route: string) => import(/* @vite-ignore */ `../${route}/route.ts`) as Promise<Record<string, unknown>>;

afterEach(() => vi.unstubAllGlobals());

describe('site -> Hermes seam: what the page sends and Hermes reads reaches Hermes', () => {
  for (const row of rows) {
    const known = KNOWN_DROPS[row.name];
    const title = known
      ? `KNOWN DROP ${row.name}: still loses ${known.dropped.join(', ')} [${known.note}]`
      : `${row.name}  [client ${row.client}]`;
    it(title, async () => {
      expect(CONTRACT[row.hermes], `Hermes has no ${row.hermes}: regenerate hermes_contract.json or fix the row`).toBeDefined();
      const sent = await sentToHermes(row, await loadRoute(row.route));
      expect(seamProblems(row, sent)).toEqual(known ? { ...CLEAN, dropped: known.dropped } : CLEAN);
    });
  }

  it('regression: the engine-note proxy before 47ad04f1 (fen only) is caught', async () => {
    const row = rows[0];
    const old = await import('./fixtures/engine-note-route.before-47ad04f1');
    const sent = await sentToHermes(row, old as Record<string, unknown>);
    expect(seamProblems(row, sent)).toEqual({ ...CLEAN, dropped: ['session_id'] });
  });
});

describe('seam coverage: no proxy or Hermes endpoint escapes the table', () => {
  const coachDir = join(dirname(fileURLToPath(import.meta.url)), '..');
  const routeFiles = (dir: string): string[] =>
    readdirSync(dir, { withFileTypes: true }).flatMap((e) =>
      e.isDirectory() ? (e.name === '__tests__' ? [] : routeFiles(join(dir, e.name))) : e.name === 'route.ts' ? [join(dir, e.name)] : []);

  it('every coach route method that takes a body is a row or listed in SITE_NOT_ROWS', () => {
    const withBody = routeFiles(coachDir).flatMap((file) => {
      const route = relative(coachDir, dirname(file)).split('\\').join('/');
      const methods = [...readFileSync(file, 'utf8').matchAll(/export async function (POST|PUT|PATCH)\b/g)].map((m) => m[1]);
      return methods.map((m) => `${route} ${m}`);
    });
    const covered = new Set([...rows.map((r) => `${r.route} ${r.method}`), ...Object.keys(SITE_NOT_ROWS)]);
    expect(withBody.filter((k) => !covered.has(k))).toEqual([]);
    expect(Object.keys(SITE_NOT_ROWS).filter((k) => !withBody.includes(k))).toEqual([]);
  });

  it('every Hermes body endpoint is a row or listed in HERMES_NOT_ROWS', () => {
    const covered = new Set([...rows.map((r) => r.hermes), ...Object.keys(HERMES_NOT_ROWS)]);
    expect(Object.keys(CONTRACT).filter((k) => !covered.has(k))).toEqual([]);
    expect(Object.keys(HERMES_NOT_ROWS).filter((k) => !(k in CONTRACT))).toEqual([]);
  });

  it('every KNOWN_DROPS entry names a row', () => {
    expect(Object.keys(KNOWN_DROPS).filter((k) => !rows.some((r) => r.name === k))).toEqual([]);
  });
});
