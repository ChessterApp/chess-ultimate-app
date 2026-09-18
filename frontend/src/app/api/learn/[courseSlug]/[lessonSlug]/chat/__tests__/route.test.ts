import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({
  auth: vi.fn(),
}));

const upsertMock = vi.fn().mockResolvedValue({ error: null });
vi.mock('@/lib/supabase-admin', () => ({
  supabaseAdmin: {
    from: vi.fn(() => ({ upsert: upsertMock })),
  },
}));

import { auth } from '@clerk/nextjs/server';

const makeParams = (courseSlug: string, lessonSlug: string) => ({
  params: Promise.resolve({ courseSlug, lessonSlug }),
});

/** Build a Response whose body is an SSE ReadableStream of the given frames. */
function sseResponse(frames: Record<string, unknown>[]) {
  const encoder = new TextEncoder();
  const body = new ReadableStream({
    start(controller) {
      for (const f of frames) {
        controller.enqueue(encoder.encode(`data: ${JSON.stringify(f)}\n\n`));
      }
      controller.close();
    },
  });
  return { ok: true, status: 200, body };
}

async function readSse(res: Response): Promise<Record<string, unknown>[]> {
  const text = await res.text();
  return text
    .split('\n')
    .filter((l) => l.startsWith('data: '))
    .map((l) => JSON.parse(l.slice(6)));
}

const HISTORY = [
  { role: 'user', content: 'earlier q' },
  { role: 'assistant', content: 'earlier a' },
];

/** Route the mocked fetch by URL: lesson GET, history GET, Hermes POST. */
function makeFetch(hermes: unknown) {
  return vi.fn((url: string) => {
    if (url.includes('/chat')) {
      // Could be the Flask history GET or the Hermes POST.
      if (url.includes('/api/lesson/chat')) return Promise.resolve(hermes as any);
      return Promise.resolve({
        ok: true,
        status: 200,
        json: async () => ({ messages: HISTORY }),
      } as any);
    }
    // Flask lesson GET
    return Promise.resolve({
      ok: true,
      status: 200,
      json: async () => ({ id: 'lesson-1', title: 'Pins', content: 'lesson body' }),
    } as any);
  });
}

describe('/api/learn/[courseSlug]/[lessonSlug]/chat proxy', () => {
  const originalFetch = global.fetch;

  beforeEach(() => {
    vi.clearAllMocks();
  });

  afterEach(() => {
    vi.restoreAllMocks();
    global.fetch = originalFetch;
  });

  it('returns 401 when not authenticated', async () => {
    (auth as any).mockResolvedValue({ userId: null });
    const { POST } = await import('../route');
    const { NextRequest } = await import('next/server');
    const req = new NextRequest('http://localhost:3000/api/learn/c/l/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message: 'hi' }),
    });
    const res = await POST(req, makeParams('c', 'l'));
    expect(res.status).toBe(401);
  });

  it('returns 400 when message is missing', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    const { POST } = await import('../route');
    const { NextRequest } = await import('next/server');
    const req = new NextRequest('http://localhost:3000/api/learn/c/l/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({}),
    });
    const res = await POST(req, makeParams('c', 'l'));
    expect(res.status).toBe(400);
  });

  it('streams deltas + done and persists the updated conversation', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    global.fetch = makeFetch(
      sseResponse([{ delta: 'A pin ' }, { delta: 'is a tactic.' }, { done: true }]),
    ) as any;

    const { POST } = await import('../route');
    const { NextRequest } = await import('next/server');
    const req = new NextRequest('http://localhost:3000/api/learn/c/l/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer tok' },
      body: JSON.stringify({ message: 'What is a pin?' }),
    });
    const res = await POST(req, makeParams('c', 'l'));
    expect(res.status).toBe(200);
    expect(res.headers.get('content-type')).toContain('text/event-stream');

    const frames = await readSse(res);
    const deltas = frames
      .filter((f) => 'delta' in f)
      .map((f) => f.delta)
      .join('');
    expect(deltas).toBe('A pin is a tactic.');
    expect(frames[frames.length - 1]).toEqual({ done: true });

    // Hermes was called with lesson context + history.
    const hermesCall = (global.fetch as any).mock.calls.find((c: any[]) =>
      c[0].includes('/api/lesson/chat'),
    );
    const sent = JSON.parse(hermesCall[1].body);
    expect(sent.message).toBe('What is a pin?');
    expect(sent.lesson_title).toBe('Pins');
    expect(sent.lesson_content).toBe('lesson body');
    expect(sent.history).toEqual(HISTORY);
    expect(hermesCall[1].headers['X-User-Id']).toBe('user_123');

    // Persisted the full conversation, not error text.
    expect(upsertMock).toHaveBeenCalledTimes(1);
    const [row, opts] = upsertMock.mock.calls[0];
    expect(row.user_id).toBe('user_123');
    expect(row.lesson_id).toBe('lesson-1');
    expect(opts).toEqual({ onConflict: 'user_id,lesson_id' });
    expect(row.messages).toEqual([
      ...HISTORY,
      { role: 'user', content: 'What is a pin?' },
      { role: 'assistant', content: 'A pin is a tactic.' },
    ]);
  });

  it('does not persist when the tutor stream errors', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_123' });
    global.fetch = makeFetch(
      sseResponse([{ error: 'Tutor error: boom' }]),
    ) as any;

    const { POST } = await import('../route');
    const { NextRequest } = await import('next/server');
    const req = new NextRequest('http://localhost:3000/api/learn/c/l/chat', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', Authorization: 'Bearer tok' },
      body: JSON.stringify({ message: 'What is a pin?' }),
    });
    const res = await POST(req, makeParams('c', 'l'));
    const frames = await readSse(res);
    expect(frames.some((f) => 'error' in f)).toBe(true);
    expect(upsertMock).not.toHaveBeenCalled();
  });
});
