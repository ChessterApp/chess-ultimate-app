import { describe, it, expect } from 'vitest';
import { classifyHermesError, coachErrorText, hermesErrorFrame, unreachableFrame } from '../coach-errors';
import ru from '../../../../messages/ru.json';
import en from '../../../../messages/en.json';
import kz from '../../../../messages/kz.json';

function translator(messages: { coach: Record<string, string> }) {
  return (key: string, values?: Record<string, string | number>) => {
    let text = messages.coach[key];
    if (text === undefined) throw new Error(`missing coach.${key}`);
    for (const [k, v] of Object.entries(values ?? {})) text = text.replace(`{${k}}`, String(v));
    return text;
  };
}

describe('classifyHermesError', () => {
  it("reads Hermes's rate-limit detail", () => {
    const c = classifyHermesError(429, { detail: { error: 'rate_limit_exceeded', message: 'Rate limit exceeded for free tier.', retry_after: 12 } });
    expect(c).toEqual({ code: 'rate_limited', message: 'Rate limit exceeded for free tier.', retryAfter: 12 });
  });

  it('reads a string detail and the known game refusals', () => {
    expect(classifyHermesError(404, { detail: 'Game not found' }).code).toBe('not_found');
    expect(classifyHermesError(400, { detail: 'It is not your move.' }).code).toBe('not_your_move');
    expect(classifyHermesError(503, { detail: 'The engine is unavailable: x' }).code).toBe('engine_unavailable');
    expect(classifyHermesError(400, { detail: 'e9 is not a legal move here.' })).toEqual({
      code: 'rejected',
      message: 'e9 is not a legal move here.',
    });
    expect(classifyHermesError(500, null).code).toBe('server');
    expect(classifyHermesError(504, null).code).toBe('unreachable');
  });
});

describe('the SSE error frames the proxies send', () => {
  it('a 429 frame carries the code and the wait', async () => {
    const res = new Response(JSON.stringify({ detail: { message: 'Rate limit exceeded', retry_after: 30 } }), { status: 429 });
    expect(await hermesErrorFrame(res)).toEqual({
      error: 'Rate limit exceeded',
      error_code: 'rate_limited',
      rate_limited: true,
      retry_after: 30,
    });
  });

  it('a body that is not JSON still gives a frame', async () => {
    expect(await hermesErrorFrame(new Response('oops', { status: 500 }))).toMatchObject({ error_code: 'server' });
  });

  it('a thrown fetch is unreachable', () => {
    expect(unreachableFrame(new Error('The operation was aborted due to timeout'))).toMatchObject({ error_code: 'unreachable' });
  });
});

describe('coachErrorText', () => {
  it('speaks every locale and puts the wait in', () => {
    for (const messages of [ru, en, kz]) {
      const t = translator(messages as { coach: Record<string, string> });
      expect(coachErrorText(t, 'rate_limited', { retryAfter: 12 })).toContain('12');
      for (const code of ['rate_limited', 'engine_unavailable', 'not_found', 'game_over', 'nothing_to_take_back', 'not_your_move', 'unreachable', 'server'] as const) {
        const text = coachErrorText(t, code);
        expect(text).not.toMatch(/Hermes|HTTP/);
        expect(text.length).toBeGreaterThan(3);
      }
    }
  });

  it("shows a refusal Hermes worded itself (an illegal move) as it is", () => {
    const t = translator(ru as { coach: Record<string, string> });
    expect(coachErrorText(t, 'rejected', { detail: 'e9 is not a legal move here.' })).toBe('e9 is not a legal move here.');
    expect(coachErrorText(t, 'rejected')).toBe(ru.coach.errorServer);
  });
});
