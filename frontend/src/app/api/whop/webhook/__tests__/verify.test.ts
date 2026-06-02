import crypto from 'crypto';
import { describe, it, expect } from 'vitest';
import { verifyWhopSignature } from '../verify';

const SECRET = 'whsec_test_phase1';
const BODY = JSON.stringify({ action: 'membership.went_valid', data: { id: 'mem_1' } });

function sign(body: string, secret: string): string {
  return crypto.createHmac('sha256', secret).update(body, 'utf8').digest('hex');
}

describe('verifyWhopSignature', () => {
  it('accepts a valid signature', () => {
    const sig = sign(BODY, SECRET);
    const res = verifyWhopSignature(BODY, sig, SECRET);
    expect(res.ok).toBe(true);
  });

  it('accepts a valid signature with sha256= prefix', () => {
    const sig = `sha256=${sign(BODY, SECRET)}`;
    const res = verifyWhopSignature(BODY, sig, SECRET);
    expect(res.ok).toBe(true);
  });

  it('rejects an invalid signature', () => {
    const res = verifyWhopSignature(BODY, 'deadbeef', SECRET);
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe('bad_signature');
  });

  it('rejects when the body has been tampered', () => {
    const sig = sign(BODY, SECRET);
    const tampered = BODY.replace('mem_1', 'mem_evil');
    const res = verifyWhopSignature(tampered, sig, SECRET);
    expect(res.ok).toBe(false);
  });

  it('rejects when signature header is missing', () => {
    const res = verifyWhopSignature(BODY, null, SECRET);
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe('no_signature');
  });

  it('fails closed when env secret is missing', () => {
    const sig = sign(BODY, SECRET);
    const res = verifyWhopSignature(BODY, sig, undefined);
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe('no_secret');
  });

  it('fails closed when env secret is empty string', () => {
    const res = verifyWhopSignature(BODY, 'abc', '');
    expect(res.ok).toBe(false);
    if (!res.ok) expect(res.reason).toBe('no_secret');
  });

  it('handles non-hex garbage in signature header without throwing', () => {
    const res = verifyWhopSignature(BODY, '~~not-hex~~', SECRET);
    expect(res.ok).toBe(false);
  });
});
