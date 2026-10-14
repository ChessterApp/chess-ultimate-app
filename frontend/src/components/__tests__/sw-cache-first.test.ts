import { describe, it, expect, vi, beforeEach } from 'vitest';
import { readFileSync } from 'fs';
import { resolve } from 'path';
import vm from 'vm';

// Executes the real public/sw.js in a sandbox and drives its fetch handler,
// so the cache-first path is tested by behaviour, not by regex.
const swSource = readFileSync(resolve(__dirname, '../../../public/sw.js'), 'utf-8');

const CSS_URL = 'https://chesster.io/_next/static/chunks/0c222ws5nk8b_.css';

function loadSw(opts: { cached?: Response; responses: Response[] }) {
  const cache = { put: vi.fn().mockResolvedValue(undefined) };
  const caches = {
    match: vi.fn().mockResolvedValue(opts.cached),
    open: vi.fn().mockResolvedValue(cache),
    keys: vi.fn().mockResolvedValue([]),
    delete: vi.fn().mockResolvedValue(true),
  };
  const queue = [...opts.responses];
  const fetch = vi.fn(async () => queue.shift() ?? new Response('', { status: 599 }));
  const listeners: Record<string, (e: unknown) => void> = {};
  const self = {
    location: { origin: 'https://chesster.io' },
    addEventListener: (type: string, fn: (e: unknown) => void) => { listeners[type] = fn; },
    skipWaiting: vi.fn(),
    clients: { claim: vi.fn() },
  };
  vm.runInNewContext(swSource, { self, caches, fetch, Response, Headers, URL });

  async function request(url: string) {
    let responded: Promise<Response> | undefined;
    const req = { url, method: 'GET', mode: 'cors', headers: new Headers() };
    listeners.fetch({ request: req, respondWith: (p: Promise<Response>) => { responded = p; } });
    const res = await responded!;
    await new Promise((r) => setTimeout(r, 0)); // let the async cache.put settle
    return res;
  }
  return { request, cache, fetch };
}

describe('sw.js cacheFirst (static assets)', () => {
  beforeEach(() => vi.clearAllMocks());

  it('never caches a 404', async () => {
    const sw = loadSw({ responses: [new Response('', { status: 404 }), new Response('', { status: 404 })] });
    const res = await sw.request(CSS_URL);
    expect(res.status).toBe(404);
    expect(sw.cache.put).not.toHaveBeenCalled();
  });

  it('retries a failed fetch bypassing the HTTP cache, then caches the good copy', async () => {
    const sw = loadSw({ responses: [new Response('', { status: 404 }), new Response('.a{}', { status: 200 })] });
    const res = await sw.request(CSS_URL);
    expect(res.status).toBe(200);
    expect(sw.fetch).toHaveBeenCalledTimes(2);
    expect(sw.fetch.mock.calls[1][1]).toEqual({ cache: 'reload' });
    expect(sw.cache.put).toHaveBeenCalledTimes(1);
  });

  it('ignores a previously cached error and refetches', async () => {
    const sw = loadSw({
      cached: new Response('', { status: 404 }),
      responses: [new Response('.a{}', { status: 200 })],
    });
    const res = await sw.request(CSS_URL);
    expect(res.status).toBe(200);
    expect(await res.text()).toBe('.a{}');
    expect(sw.cache.put).toHaveBeenCalledTimes(1);
  });

  it('serves a cached 200 without hitting the network', async () => {
    const sw = loadSw({ cached: new Response('.cached{}', { status: 200 }), responses: [] });
    const res = await sw.request(CSS_URL);
    expect(await res.text()).toBe('.cached{}');
    expect(sw.fetch).not.toHaveBeenCalled();
  });

  it('caches a fresh 200 on a miss', async () => {
    const sw = loadSw({ responses: [new Response('.a{}', { status: 200 })] });
    const res = await sw.request(CSS_URL);
    expect(res.status).toBe(200);
    expect(sw.fetch).toHaveBeenCalledTimes(1);
    expect(sw.cache.put).toHaveBeenCalledTimes(1);
  });
});
