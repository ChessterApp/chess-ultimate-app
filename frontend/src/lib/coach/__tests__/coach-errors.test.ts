import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
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
      code: 'illegal_move',
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

  it('a refusal without its text is the general line', () => {
    const t = translator(ru as { coach: Record<string, string> });
    expect(coachErrorText(t, 'rejected')).toBe(ru.coach.errorServer);
  });
});

// Site review 28.10: Hermes's GameError texts and the proxies' own texts reached the ru/kz student in English
// («Ход не принят: e9 is not a legal move here.», «Unauthorized», «Hermes error: 404»).
describe('English refusals become the student language', () => {
  const ENGLISH = /legal move|Cannot read|Unauthorized|Hermes|HTTP|not a game|side line|color must/i;
  const shown = (messages: unknown, status: number, body: unknown) => {
    const t = translator(messages as { coach: Record<string, string> });
    const c = classifyHermesError(status, body);
    return coachErrorText(t, c.code, { retryAfter: c.retryAfter, detail: c.message });
  };
  let warn: ReturnType<typeof vi.spyOn>;
  beforeEach(() => {
    warn = vi.spyOn(console, 'warn').mockImplementation(() => {});
  });
  afterEach(() => warn.mockRestore());

  it('an illegal move keeps the move and drops the English', () => {
    for (const messages of [ru, kz]) {
      const text = shown(messages, 400, { error: 'Hermes error: 400', detail: { detail: 'e9 is not a legal move here.' } });
      expect(text).toContain('e9');
      expect(text).not.toMatch(ENGLISH);
    }
    expect(shown(ru, 400, { detail: 'e9 is not a legal move here.' })).toBe(ru.coach.errorIllegalMove.replace('{move}', 'e9'));
  });

  it('a move Hermes could not read', () => {
    const text = shown(ru, 400, { detail: "Cannot read the move 'Kx'." });
    expect(text).toBe(ru.coach.errorUnreadableMove.replace('{move}', 'Kx'));
    expect(shown(kz, 400, { detail: 'Empty move.' })).toBe(kz.coach.errorEmptyMove);
  });

  it("the proxy's own «Unauthorized» (401) is a sign-in line", () => {
    const c = classifyHermesError(401, { error: 'Unauthorized' });
    expect(c.code).toBe('unauthorized');
    expect(shown(ru, 401, { error: 'Unauthorized' })).toBe(ru.coach.errorUnauthorized);
  });

  it("a 404 whose body was not Hermes's («Hermes error: 404», «Unknown action») is not_found", () => {
    expect(classifyHermesError(404, { error: 'Hermes error: 404' }).code).toBe('not_found');
    expect(classifyHermesError(404, { error: 'Unknown action' }).code).toBe('not_found');
    expect(shown(ru, 404, { error: 'Hermes error: 404' })).toBe(ru.coach.errorNotFound);
  });

  it('any other English refusal is a general line in the student language; the original goes to the console', () => {
    for (const detail of ['color must be white, black or random', "The side line does not replay from the game's position.", 'Missing fen']) {
      const text = shown(ru, 400, { detail });
      expect(text).toBe(ru.coach.errorRejected);
      expect(warn).toHaveBeenCalledWith(expect.any(String), detail);
    }
  });

  it('every locale has the texts', () => {
    for (const messages of [ru, en, kz]) {
      const t = translator(messages as { coach: Record<string, string> });
      for (const code of ['unauthorized', 'illegal_move', 'unreadable_move', 'rejected'] as const) {
        expect(coachErrorText(t, code, { detail: 'e9 is not a legal move here.' }).length).toBeGreaterThan(3);
      }
    }
  });
});
