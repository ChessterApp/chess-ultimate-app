// @vitest-environment jsdom
/**
 * Unit tests for the client 403 fallback (`access-fetch`): a
 * MEMBERSHIP_RESTRICTED 403 is detected and redirects to the upgrade path;
 * everything else is left alone.
 */
import { describe, it, expect, beforeEach } from 'vitest';
import { readRestricted, handleRestrictedResponse } from '../access-fetch';

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { 'Content-Type': 'application/json' },
  });
}

beforeEach(() => {
  // jsdom provides window.location; make href assignable + observable.
  Object.defineProperty(window, 'location', {
    value: { href: '' },
    writable: true,
  });
});

describe('readRestricted', () => {
  it('parses a MEMBERSHIP_RESTRICTED 403 body', async () => {
    const res = jsonResponse(
      { error: 'MEMBERSHIP_RESTRICTED', reason: 'frozen', upgradePath: '/upgrade/continue' },
      403,
    );
    expect(await readRestricted(res)).toEqual({
      reason: 'frozen',
      upgradePath: '/upgrade/continue',
    });
  });

  it('falls back to /dashboard when upgradePath is missing', async () => {
    const res = jsonResponse({ error: 'MEMBERSHIP_RESTRICTED', reason: 'expired' }, 403);
    expect(await readRestricted(res)).toEqual({
      reason: 'expired',
      upgradePath: '/dashboard',
    });
  });

  it('ignores a non-403 response', async () => {
    expect(await readRestricted(jsonResponse({ error: 'nope' }, 500))).toBeNull();
  });

  it('ignores a 403 that is not our envelope', async () => {
    expect(await readRestricted(jsonResponse({ error: 'Forbidden' }, 403))).toBeNull();
  });

  it('leaves the original body readable (reads a clone)', async () => {
    const res = jsonResponse(
      { error: 'MEMBERSHIP_RESTRICTED', reason: 'frozen', upgradePath: '/x' },
      403,
    );
    await readRestricted(res);
    // Original body still consumable by the caller.
    expect(await res.json()).toMatchObject({ error: 'MEMBERSHIP_RESTRICTED' });
  });
});

describe('handleRestrictedResponse', () => {
  it('redirects and returns true on a restricted 403', async () => {
    const res = jsonResponse(
      { error: 'MEMBERSHIP_RESTRICTED', reason: 'frozen', upgradePath: '/upgrade/continue' },
      403,
    );
    expect(await handleRestrictedResponse(res)).toBe(true);
    expect(window.location.href).toBe('/upgrade/continue');
  });

  it('returns false and does not redirect otherwise', async () => {
    const res = jsonResponse({ ok: true }, 200);
    expect(await handleRestrictedResponse(res)).toBe(false);
    expect(window.location.href).toBe('');
  });
});
