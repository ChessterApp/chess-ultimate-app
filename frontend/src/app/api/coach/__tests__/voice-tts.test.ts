import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

vi.mock('@clerk/nextjs/server', () => ({ auth: vi.fn() }));
vi.mock('@/lib/coach-access', () => ({ requireCoachAccess: vi.fn(async () => null) }));

import { auth } from '@clerk/nextjs/server';

const makeRequest = (body?: unknown) =>
  new Request('http://localhost:3000/api/coach/voice/tts', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: body === undefined ? undefined : JSON.stringify(body),
  });

/** An SSE body the way Gemini TTS streams it: two audio parts, base64. */
function sseBody(parts: Buffer[]): ReadableStream<Uint8Array> {
  const enc = new TextEncoder();
  const lines = parts.map((p) => `data: ${JSON.stringify({ candidates: [{ content: { parts: [{ inlineData: { mimeType: 'audio/l16;rate=24000', data: p.toString('base64') } }] } }] })}\n\n`);
  return new ReadableStream({
    start(controller) {
      for (const l of lines) controller.enqueue(enc.encode(l));
      controller.close();
    },
  });
}

describe('POST /api/coach/voice/tts (the voice pipeline, 25.10)', () => {
  const originalKey = process.env.GEMINI_API_KEY;
  beforeEach(() => { vi.clearAllMocks(); process.env.GEMINI_API_KEY = 'AQ.test-key'; });
  afterEach(() => { if (originalKey === undefined) delete process.env.GEMINI_API_KEY; else process.env.GEMINI_API_KEY = originalKey; vi.restoreAllMocks(); });

  it('reads one sentence aloud: the audio bytes stream back, the key stays on the server', async () => {
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    const a = Buffer.from([1, 0, 2, 0]), b = Buffer.from([3, 0]);
    const fetchMock = vi.fn(async () => ({ ok: true, body: sseBody([a, b]), text: async () => '' }));
    global.fetch = fetchMock as any;
    const { POST } = await import('../voice/tts/route');
    const res = await POST(makeRequest({ text: 'Сейчас посмотрю на позицию.', locale: 'ru' }));
    expect(res.status).toBe(200);
    expect(res.headers.get('Content-Type')).toBe('application/octet-stream');
    expect(res.headers.get('X-Sample-Rate')).toBe('24000');
    const bytes = Buffer.from(await res.arrayBuffer());
    expect([...bytes]).toEqual([1, 0, 2, 0, 3, 0]);
    const [url, init] = fetchMock.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toContain('gemini-3.8-flash-tts:streamGenerateContent?alt=sse');
    expect((init.headers as Record<string, string>)['x-goog-api-key']).toBe('AQ.test-key');
    const sent = JSON.parse(init.body as string);
    expect(sent.contents[0].parts[0].text).toBe('Сейчас посмотрю на позицию.');
    expect(sent.generationConfig.responseModalities).toEqual(['AUDIO']);
  });

  it('refuses without a user, without text, and reports an upstream failure', async () => {
    (auth as any).mockResolvedValue({ userId: null });
    const { POST } = await import('../voice/tts/route');
    expect((await POST(makeRequest({ text: 'x' }))).status).toBe(401);
    (auth as any).mockResolvedValue({ userId: 'user_1' });
    expect((await POST(makeRequest({}))).status).toBe(400);
    global.fetch = vi.fn(async () => ({ ok: false, status: 429, body: null, text: async () => 'quota' })) as any;
    expect((await POST(makeRequest({ text: 'Привет' }))).status).toBe(502);
  });
});
