// @vitest-environment jsdom
import { afterEach, describe, expect, it, vi } from 'vitest';
import { chosenVoiceMode, fetchServerVoiceMode, readVoiceMode } from '../usePipelineVoice';

/** 17.11: the voice mode is the student's choice when there is one (the address, an earlier visit, the build);
 *  otherwise the coach server names it, and the page is on Gemini Live until it has. */
afterEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, '', '/coach');
  vi.unstubAllGlobals();
  vi.unstubAllEnvs();
});

describe('the chosen voice mode', () => {
  it('is nobody’s until the address or an earlier visit says', () => {
    expect(chosenVoiceMode()).toBeNull();
    expect(readVoiceMode()).toBe('live');
    window.history.replaceState(null, '', '/coach?voice=pipeline');
    expect(chosenVoiceMode()).toBe('pipeline');
    window.history.replaceState(null, '', '/coach');
    expect(chosenVoiceMode()).toBe('pipeline');   // remembered
    window.history.replaceState(null, '', '/coach?voice=live');
    expect(readVoiceMode()).toBe('live');
    window.history.replaceState(null, '', '/coach');
    expect(chosenVoiceMode()).toBe('live');       // Live chosen stays chosen: the server's default does not override it
  });

  it('is the build’s when the build names one', () => {
    vi.stubEnv('NEXT_PUBLIC_COACH_VOICE_MODE', 'pipeline');
    expect(chosenVoiceMode()).toBe('pipeline');
  });
});

describe('the server’s voice mode', () => {
  const answer = (status: number, body: unknown) => vi.stubGlobal('fetch', vi.fn(async () => new Response(JSON.stringify(body), { status })));

  it('is read from the coach server', async () => {
    answer(200, { mode: 'pipeline' });
    expect(await fetchServerVoiceMode()).toBe('pipeline');
    expect(fetch).toHaveBeenCalledWith('/api/coach/voice/mode', expect.anything());
    answer(200, { mode: 'live' });
    expect(await fetchServerVoiceMode()).toBe('live');
  });

  it('is unknown with an older server, a strange answer or no network', async () => {
    answer(404, { error: 'Hermes error: 404' });
    expect(await fetchServerVoiceMode()).toBeNull();
    answer(200, { mode: 'telepathy' });
    expect(await fetchServerVoiceMode()).toBeNull();
    vi.stubGlobal('fetch', vi.fn(async () => { throw new TypeError('Failed to fetch'); }));
    expect(await fetchServerVoiceMode()).toBeNull();
  });
});
