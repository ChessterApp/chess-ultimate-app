/**
 * Tests for invite-jwt.ts — sign/verify round-trip, expiry, tampering.
 */
import { createHash } from 'node:crypto';
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import {
  signInviteJwt,
  verifyInviteJwt,
  jwtJtiHash,
  InviteJwtError,
  INVITE_JWT_TTL_SECONDS,
  INVITE_JWT_CLAIM_GRACE_SECONDS,
} from '../invite-jwt';

const payload = {
  student_id: '00000000-0000-0000-0000-000000000001',
  branch_id: '00000000-0000-0000-0000-000000000002',
  branch_token_id: '00000000-0000-0000-0000-000000000003',
  org_id: '00000000-0000-0000-0000-000000000004',
};

describe('invite-jwt', () => {
  const originalSecret = process.env.INVITE_JWT_SECRET;
  beforeEach(() => {
    process.env.INVITE_JWT_SECRET = 'unit-test-secret';
  });
  afterEach(() => {
    if (originalSecret === undefined) delete process.env.INVITE_JWT_SECRET;
    else process.env.INVITE_JWT_SECRET = originalSecret;
  });

  it('defaults the TTL to 15 minutes', () => {
    expect(INVITE_JWT_TTL_SECONDS).toBe(15 * 60);
  });

  it('bakes the 15-minute TTL into the default exp', () => {
    const now = 1_700_000_000;
    const token = signInviteJwt(payload, undefined, now);
    const claims = verifyInviteJwt(token, now);
    expect(claims.exp).toBe(now + 900);
  });

  it('signs and verifies a round-trip', () => {
    const now = 1_700_000_000;
    const token = signInviteJwt(payload, INVITE_JWT_TTL_SECONDS, now);
    const claims = verifyInviteJwt(token, now);
    expect(claims.student_id).toBe(payload.student_id);
    expect(claims.branch_id).toBe(payload.branch_id);
    expect(claims.branch_token_id).toBe(payload.branch_token_id);
    expect(claims.org_id).toBe(payload.org_id);
    expect(claims.exp).toBe(now + INVITE_JWT_TTL_SECONDS);
    expect(claims.iat).toBe(now);
  });

  it('rejects expired tokens', () => {
    const now = 1_700_000_000;
    const token = signInviteJwt(payload, 60, now);
    expect(() => verifyInviteJwt(token, now + 61)).toThrowError(InviteJwtError);
  });

  it('rejects tampered signatures', () => {
    const token = signInviteJwt(payload);
    const tampered = token.slice(0, -4) + 'AAAA';
    expect(() => verifyInviteJwt(tampered)).toThrowError(/signature/i);
  });

  it('rejects tampered payloads', () => {
    const token = signInviteJwt(payload);
    const [h, p, s] = token.split('.');
    expect(h).toBeDefined();
    expect(p).toBeDefined();
    expect(s).toBeDefined();
    const fudged = `${h}.${p.slice(0, -1)}A.${s}`;
    expect(() => verifyInviteJwt(fudged)).toThrowError(/signature/i);
  });

  it('rejects malformed tokens', () => {
    expect(() => verifyInviteJwt('not-a-jwt')).toThrowError(/malformed/i);
  });

  it('rejects when secret is missing', () => {
    delete process.env.INVITE_JWT_SECRET;
    expect(() => signInviteJwt(payload)).toThrowError(/INVITE_JWT_SECRET/);
  });

  it('carries a member_type=coach claim through a round-trip', () => {
    const token = signInviteJwt({ ...payload, member_type: 'coach' });
    const claims = verifyInviteJwt(token);
    expect(claims.member_type).toBe('coach');
  });

  it('defaults member_type to student when the claim is absent (back-compat)', () => {
    // Legacy tokens were signed with no member_type field.
    const token = signInviteJwt(payload);
    expect(token.split('.').length).toBe(3);
    const claims = verifyInviteJwt(token);
    expect(claims.member_type).toBe('student');
  });

  it('normalizes an unknown member_type value to student', () => {
    const token = signInviteJwt({
      ...payload,
      member_type: 'admin' as unknown as 'coach',
    });
    const claims = verifyInviteJwt(token);
    expect(claims.member_type).toBe('student');
  });

  describe('grace window', () => {
    const now = 1_700_000_000;

    it('exposes a 24-hour claim grace constant', () => {
      expect(INVITE_JWT_CLAIM_GRACE_SECONDS).toBe(24 * 60 * 60);
    });

    it('defaults to strict (grace 0): expired one second past exp is rejected', () => {
      const token = signInviteJwt(payload, 60, now); // exp = now + 60
      expect(() => verifyInviteJwt(token, now + 61)).toThrowError(/expired/i);
    });

    it('accepts a valid signature expired within the grace window', () => {
      const token = signInviteJwt(payload, 60, now); // exp = now + 60
      // now + 120 is 60s past exp, well within a 100s grace window.
      const claims = verifyInviteJwt(token, now + 120, 100);
      expect(claims.student_id).toBe(payload.student_id);
    });

    it('accepts exactly at the grace boundary (exp + grace === now)', () => {
      const token = signInviteJwt(payload, 60, now); // exp = now + 60
      // now = exp + grace exactly → still accepted (boundary is inclusive).
      expect(() => verifyInviteJwt(token, now + 160, 100)).not.toThrow();
    });

    it('rejects a signature expired beyond the grace window', () => {
      const token = signInviteJwt(payload, 60, now); // exp = now + 60
      expect(() => verifyInviteJwt(token, now + 161, 100)).toThrowError(/expired/i);
    });

    it('rejects a bad signature even within the grace window', () => {
      const token = signInviteJwt(payload, 60, now).slice(0, -4) + 'AAAA';
      expect(() => verifyInviteJwt(token, now + 120, 100)).toThrowError(/signature/i);
    });

    it('accepts a still-valid token within grace (grace never shrinks validity)', () => {
      const token = signInviteJwt(payload, 900, now);
      const claims = verifyInviteJwt(token, now + 100, INVITE_JWT_CLAIM_GRACE_SECONDS);
      expect(claims.org_id).toBe(payload.org_id);
    });
  });

  it('rejects payloads missing required claims', () => {
    const token = signInviteJwt(payload);
    // Re-sign with a deliberately broken payload — same secret, broken claim.
    process.env.INVITE_JWT_SECRET = 'unit-test-secret';
    const otherToken = signInviteJwt({ ...payload, org_id: '' as string });
    // org_id empty: signInviteJwt allows it (no input validation), but verify
    // should reject "missing required claim".
    expect(() => verifyInviteJwt(otherToken)).toThrowError(/required claim/i);
    // Sanity: the original still passes.
    expect(verifyInviteJwt(token)).toBeDefined();
  });
});

describe('jwtJtiHash', () => {
  it('is deterministic across calls', () => {
    const token = 'eyJhbGciOiJIUzI1NiJ9.eyJ0ZXN0Ijp0cnVlfQ.signature';
    expect(jwtJtiHash(token)).toBe(jwtJtiHash(token));
  });

  it('matches the reference sha256 hex encoding', () => {
    const token = 'sample.jwt.token';
    const expected = createHash('sha256').update(token, 'utf8').digest('hex');
    const got = jwtJtiHash(token);
    expect(got).toBe(expected);
    expect(got).toHaveLength(64);
    expect(/^[0-9a-f]{64}$/.test(got)).toBe(true);
  });

  it('produces different hashes for different tokens', () => {
    expect(jwtJtiHash('token-a.header.sig')).not.toBe(jwtJtiHash('token-b.header.sig'));
  });
});
