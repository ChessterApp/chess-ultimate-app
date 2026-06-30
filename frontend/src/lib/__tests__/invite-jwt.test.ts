/**
 * Tests for invite-jwt.ts — sign/verify round-trip, expiry, tampering.
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest';

import {
  signInviteJwt,
  verifyInviteJwt,
  InviteJwtError,
  INVITE_JWT_TTL_SECONDS,
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
