/**
 * @vitest-environment jsdom
 */
import { describe, it, expect, beforeEach } from 'vitest';
import {
  LEGACY_SESSION_KEY,
  clearSessionId,
  loadSessionId,
  saveSessionId,
  sessionKey,
} from '../session-storage';

describe('coach session storage', () => {
  beforeEach(() => localStorage.clear());

  it('keeps one session id per user', () => {
    saveSessionId('user_a', 'sess-a');
    saveSessionId('user_b', 'sess-b');
    expect(loadSessionId('user_a')).toBe('sess-a');
    expect(loadSessionId('user_b')).toBe('sess-b');
  });

  it("does not hand one user's session to another", () => {
    saveSessionId('user_a', 'sess-a');
    expect(loadSessionId('user_b')).toBeNull();
  });

  it('moves the legacy shared key to the current user once', () => {
    localStorage.setItem(LEGACY_SESSION_KEY, 'old-sess');
    expect(loadSessionId('user_a')).toBe('old-sess');
    expect(localStorage.getItem(LEGACY_SESSION_KEY)).toBeNull();
    expect(localStorage.getItem(sessionKey('user_a'))).toBe('old-sess');
    expect(loadSessionId('user_b')).toBeNull();
  });

  it('prefers the per-user key over the legacy key', () => {
    saveSessionId('user_a', 'sess-a');
    localStorage.setItem(LEGACY_SESSION_KEY, 'old-sess');
    expect(loadSessionId('user_a')).toBe('sess-a');
  });

  it('clears only that user', () => {
    saveSessionId('user_a', 'sess-a');
    saveSessionId('user_b', 'sess-b');
    clearSessionId('user_a');
    expect(loadSessionId('user_a')).toBeNull();
    expect(loadSessionId('user_b')).toBe('sess-b');
  });
});
