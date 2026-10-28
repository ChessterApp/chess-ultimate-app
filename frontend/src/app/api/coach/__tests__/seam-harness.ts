/**
 * Route-driven seam harness (28.10). The table test (seam.contract.test.ts) copies each page body
 * by hand, so a body the page changes later is not what it checks. Here the REAL caller (the voice
 * hook, the chat page) runs with fetch routed into the REAL Next route handlers; only Hermes
 * (HERMES_URL) is stubbed. Every body that reaches Hermes is recorded against the site call that
 * caused it and checked against Hermes's request model (hermes_contract.json).
 *
 * The test files keep their own vi.mock calls (Clerk, access, tier, analytics, @google/genai):
 * mocks are per test file and must be hoisted there.
 */
import { AsyncLocalStorage } from 'node:async_hooks';
import contractJson from './hermes_contract.json';

export const HERMES = 'http://hermes.test';

type Contract = Record<string, { model: string | null; fields: string[] | null }>;
const CONTRACT = contractJson as Contract;

type Json = Record<string, unknown>;
type RouteModule = Record<string, unknown>;
type Handler = (req: unknown, ctx: { params: Promise<Record<string, string>> }) => Promise<Response>;

export type HermesCall = { method: string; path: string; body: Json | null };
export type SiteCall = { path: string; method: string; sent: Json; status: number; hermes: HermesCall[] };

/** Where each site path the callers use is served (folder under app/api/coach) and its route params. */
function siteRoute(path: string): { route: string; params: Record<string, string> } | null {
  const p = path.replace(/^\/api\/coach\//, '');
  let m: RegExpMatchArray | null;
  if ((m = p.match(/^sessions\/([^/]+)\/messages$/))) return { route: 'sessions/[id]/messages', params: { id: decodeURIComponent(m[1]) } };
  if ((m = p.match(/^sessions\/([^/]+)$/))) return { route: 'sessions/[id]', params: { id: decodeURIComponent(m[1]) } };
  if ((m = p.match(/^sessions\/([^/]+)\/game\/([^/]+)\/([^/]+)$/))) {
    return { route: 'sessions/[id]/game/[boardId]/[action]', params: { id: m[1], boardId: m[2], action: m[3] } };
  }
  const flat = ['live-token', 'voice/engine-note', 'voice/idea', 'voice/check', 'voice/intent', 'voice/tts', 'tool',
    'voice-usage', 'metrics', 'chat', 'feedback', 'sessions', 'import-url'];
  return flat.includes(p) ? { route: p, params: {} } : null;
}

/**
 * Site call (path + method) -> the Hermes body endpoint it must reach. `proxyReads`: fields the caller
 * sends that the proxy consumes itself, with how to see they arrived. null: no request model to check.
 */
type Seam = { hermes: string; at: RegExp; proxyReads?: Record<string, (hermesPath: string, value: unknown) => boolean> };
const SEAMS: Record<string, Seam | null> = {
  'POST voice/engine-note': { hermes: 'POST /api/coach/voice/engine-note', at: /^\/api\/coach\/voice\/engine-note$/ },
  'POST voice/idea': { hermes: 'POST /api/coach/voice/idea', at: /^\/api\/coach\/voice\/idea$/ },
  'POST voice/check': { hermes: 'POST /api/coach/voice/check', at: /^\/api\/coach\/voice\/check$/ },
  'POST voice/intent': { hermes: 'POST /api/coach/voice/intent', at: /^\/api\/coach\/voice\/intent$/ },
  'POST voice/tts': { hermes: 'POST /api/coach/voice/tts', at: /^\/api\/coach\/voice\/tts$/ },
  'POST tool': {
    hermes: 'POST /api/coach/tool/{name}', at: /^\/api\/coach\/tool\/[^/]+$/,
    proxyReads: { name: (path, v) => path === `/api/coach/tool/${encodeURIComponent(String(v))}` },
  },
  'POST live-token': {
    hermes: 'POST /api/coach/voice/prompt', at: /^\/api\/coach\/voice\/prompt$/,
    // The hook resumes the Live session itself with the handle; no server side reads it.
    proxyReads: { resume: () => true },
  },
  'POST voice-usage': { hermes: 'POST /internal/voice/heartbeat', at: /^\/internal\/voice\/heartbeat$/ },
  'POST chat': { hermes: 'POST /api/coach/chat', at: /^\/api\/coach\/chat$/ },
  'POST feedback': { hermes: 'POST /api/coach/feedback', at: /^\/api\/coach\/feedback$/ },
  'POST sessions/[id]/messages': { hermes: 'POST /api/coach/sessions/{session_id}/messages', at: /^\/api\/coach\/sessions\/[^/]+\/messages$/ },
  'POST sessions': { hermes: 'POST /api/coach/sessions', at: /^\/api\/coach\/sessions$/ },
  'POST import-url': { hermes: 'POST /api/coach/import-url', at: /^\/api\/coach\/import-url$/ },
  'POST metrics': null,  // Hermes reads a raw dict
};

/** Hermes GETs the proxies make on the side (no body, nothing to check). */
const HERMES_READS = [/^\/api\/coach\/tools$/, /^\/internal\/voice\/quota$/, /^\/api\/coach\/sessions\/[^/]+\/messages$/, /^\/api\/coach\/sessions\/[^/]+$/];

/** The body the site call delivered to its own Hermes endpoint (not the side calls its proxy makes). */
export function hermesBody(call: SiteCall): Json | null | undefined {
  const route = siteRoute(call.path);
  const seam = route ? SEAMS[`${call.method} ${route.route}`] : null;
  return seam ? call.hermes.find((x) => x.method === 'POST' && seam.at.test(x.path))?.body : undefined;
}

export type Problems = { dropped: string[]; unknown: string[]; orphan: string[]; reached: string[] };
export const CLEAN: Problems = { dropped: [], unknown: [], orphan: [], reached: [] };

/**
 * What is wrong with one site call's trip to Hermes:
 *  - dropped: a field the caller sent and Hermes reads did not arrive unchanged;
 *  - unknown: a field reached Hermes that its model does not declare (pydantic drops it silently);
 *  - orphan:  a field the caller sent that neither Hermes nor the proxy reads;
 *  - reached: the call did not reach its Hermes endpoint exactly once.
 */
export function seamProblems(call: SiteCall): Problems {
  const route = siteRoute(call.path);
  const seam = route ? SEAMS[`${call.method} ${route.route}`] : undefined;
  if (seam === null || (route && call.method === 'GET')) return CLEAN;  // no body to carry
  if (!seam) return { ...CLEAN, reached: [`no seam known for ${call.method} ${call.path}`] };
  const declared = CONTRACT[seam.hermes]?.fields;
  if (!declared) return { ...CLEAN, reached: [`hermes_contract.json has no fields for ${seam.hermes}`] };
  const hits = call.hermes.filter((h) => h.method === 'POST' && seam.at.test(h.path));
  if (hits.length !== 1) return { ...CLEAN, reached: [`${hits.length} requests to ${seam.hermes} (site answered ${call.status})`] };
  const { path, body } = hits[0];
  const got = body ?? {};
  const present = Object.keys(got).filter((k) => got[k] !== undefined);
  const proxyReads = seam.proxyReads ?? {};
  const sentKeys = Object.keys(call.sent).filter((k) => call.sent[k] !== undefined);
  return {
    dropped: sentKeys.filter((k) => (declared.includes(k)
      ? JSON.stringify(got[k]) !== JSON.stringify(call.sent[k])
      : k in proxyReads && !proxyReads[k](path, call.sent[k]))),
    unknown: present.filter((k) => !declared.includes(k)),
    orphan: sentKeys.filter((k) => !declared.includes(k) && !(k in proxyReads)),
    reached: [],
  };
}

export type Harness = {
  /** Every site call made so far, in order. */
  calls: SiteCall[];
  /** Fetches that went nowhere known (a site path with no route here, or a Hermes path outside the contract). */
  strays: string[];
  /** Hermes's answer per path (JSON, or a whole Response); the default covers the side reads. */
  reply: (path: string, body: Json | null) => unknown;
  /** Route modules swapped for a test (key: folder under app/api/coach). */
  overrides: Record<string, RouteModule>;
  fetch: (input: unknown, init?: RequestInit) => Promise<Response>;
  /** The finished site calls to `path` (exact, without the query). */
  to: (path: string) => SiteCall[];
  /** Resolves when every site call started so far has answered (fire-and-forget ones too). */
  settled: () => Promise<void>;
  /** Every site call's problems, keyed by call; empty when the seam is clean. */
  problems: () => Record<string, Problems>;
};

export const defaultHermesReply = (path: string): unknown => {
  if (path === '/api/coach/tools') return { tools: [] };
  if (path === '/api/coach/voice/prompt') return { system_prompt: 'You are the coach.' };
  if (path === '/api/coach/voice/intent') return { kind: 'none' };
  if (path.endsWith('/messages')) return { messages: [] };
  return {};
};

const json = (data: unknown, status = 200) =>
  new Response(JSON.stringify(data), { status, headers: { 'content-type': 'application/json' } });

// One store for every harness: a proxy still running from an earlier test is then seen as its own call.
const current = new AsyncLocalStorage<SiteCall>();

export function createHarness(opts: { cookie?: string } = {}): Harness {
  const pending = new Set<Promise<unknown>>();
  const modules = new Map<string, Promise<RouteModule>>();
  const load = (route: string) => {
    if (!modules.has(route)) modules.set(route, import(/* @vite-ignore */ `../${route}/route.ts`) as Promise<RouteModule>);
    return modules.get(route)!;
  };

  const h: Harness = {
    calls: [],
    strays: [],
    reply: defaultHermesReply,
    overrides: {},
    async fetch(input, init) {
      const url = String(input instanceof Request ? input.url : input);
      if (url.startsWith(HERMES)) {
        const u = new URL(url);
        const method = (init?.method ?? 'GET').toUpperCase();
        const body = typeof init?.body === 'string' && init.body ? (JSON.parse(init.body) as Json) : null;
        const site = current.getStore();
        const known = method === 'GET' ? HERMES_READS.some((r) => r.test(u.pathname))
          : Object.keys(CONTRACT).some((k) => k.startsWith(`${method} `) && contractRe(k).test(u.pathname));
        if (!known) h.strays.push(`Hermes ${method} ${u.pathname}`);
        if (site && h.calls.includes(site)) site.hermes.push({ method, path: u.pathname, body });
        else h.strays.push(`Hermes ${method} ${u.pathname} outside a site call of this test`);
        const answer = h.reply(u.pathname, body);
        return answer instanceof Response ? answer : json(answer);
      }
      const path = url.split('?')[0];
      const route = path.startsWith('/api/coach/') ? siteRoute(path) : null;
      if (!route) {
        h.strays.push(`site ${url}`);
        throw new Error(`no route under test for ${url}`);
      }
      const method = (init?.method ?? 'GET').toUpperCase();
      const raw = typeof init?.body === 'string' ? init.body : undefined;
      const call: SiteCall = { path, method, sent: raw ? (JSON.parse(raw) as Json) : {}, status: 0, hermes: [] };
      h.calls.push(call);
      // Read the whole answer inside the call: streaming proxies call Hermes while the body is read.
      const run = current.run(call, async () => {
        const mod = h.overrides[route.route] ?? (await load(route.route));
        const handler = mod[method] as Handler | undefined;
        if (!handler) throw new Error(`${route.route} exports no ${method}`);
        const { NextRequest } = await import('next/server');
        // No signal: the hook's AbortSignal is jsdom's, which Node's Request refuses.
        const headers = new Headers(init?.headers as HeadersInit | undefined);
        if (opts.cookie) headers.set('cookie', opts.cookie);
        const req = new NextRequest(`http://localhost${url}`, { method, headers, body: raw });
        const res = await handler(req, { params: Promise.resolve(route.params) });
        const buf = await res.arrayBuffer();
        call.status = res.status;
        return new Response(buf, { status: res.status, headers: res.headers });
      });
      pending.add(run);
      void run.catch(() => {}).finally(() => pending.delete(run));
      return run;
    },
    to: (path) => h.calls.filter((c) => c.path === path && c.status !== 0),
    async settled() {
      while (pending.size) await Promise.allSettled([...pending]);
    },
    problems() {
      const out: Record<string, Problems> = {};
      h.calls.forEach((c, i) => {
        const p = seamProblems(c);
        if (JSON.stringify(p) !== JSON.stringify(CLEAN)) out[`#${i} ${c.method} ${c.path} ${JSON.stringify(c.sent)}`] = p;
      });
      if (h.strays.length) out.strays = { ...CLEAN, reached: h.strays };
      return out;
    },
  };
  return h;
}

/** 'POST /api/coach/tool/{name}' -> a regex for its concrete paths. */
function contractRe(key: string): RegExp {
  const tpl = key.slice(key.indexOf(' ') + 1).replace(/[.*+?^$()|[\]\\]/g, '\\$&').replace(/\{[^}]+\}/g, '[^/]+');
  return new RegExp(`^${tpl}$`);
}
