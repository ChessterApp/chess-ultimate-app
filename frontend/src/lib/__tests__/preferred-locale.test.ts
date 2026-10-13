// @vitest-environment jsdom
import { describe, it, expect, vi, afterEach } from 'vitest';
import { persistPreferredLocale, PERSIST_WAIT_MS } from '../preferred-locale';

function setClerkUser(user: unknown) {
  (window as unknown as { Clerk?: unknown }).Clerk = user === undefined ? undefined : { user };
}

describe('persistPreferredLocale', () => {
  afterEach(() => {
    setClerkUser(undefined);
    vi.useRealTimers();
  });

  it('merges preferred_locale into existing unsafeMetadata', async () => {
    const update = vi.fn().mockResolvedValue({});
    setClerkUser({ unsafeMetadata: { onboardingAnswers: { a: 1 } }, update });
    await persistPreferredLocale('kz');
    expect(update).toHaveBeenCalledWith({
      unsafeMetadata: { onboardingAnswers: { a: 1 }, preferred_locale: 'kz' },
    });
  });

  it('is a no-op when signed out', async () => {
    setClerkUser(null);
    await expect(persistPreferredLocale('ru')).resolves.toBeUndefined();
  });

  it('swallows update failures (sync throw or rejection)', async () => {
    setClerkUser({ update: vi.fn().mockRejectedValue(new Error('net')) });
    await expect(persistPreferredLocale('en')).resolves.toBeUndefined();
    setClerkUser({ update: vi.fn(() => { throw new Error('boom'); }) });
    await expect(persistPreferredLocale('en')).resolves.toBeUndefined();
  });

  it('resolves after the wait cap when Clerk hangs', async () => {
    vi.useFakeTimers();
    setClerkUser({ update: vi.fn(() => new Promise(() => {})) });
    const done = vi.fn();
    persistPreferredLocale('ru').then(done);
    await vi.advanceTimersByTimeAsync(PERSIST_WAIT_MS);
    expect(done).toHaveBeenCalled();
  });
});
