import crypto from 'crypto';

/**
 * Verify a Whop webhook HMAC SHA-256 signature.
 *
 * Whop sends an `X-Whop-Signature` header containing an HMAC SHA-256 hex
 * digest of the raw request body, keyed with `WHOP_WEBHOOK_SECRET`.
 *
 * Returns a discriminated result so the caller can map to the right HTTP
 * status (401 on bad/missing sig, 500 on missing env var = fail closed).
 */

export type VerifyResult =
  | { ok: true }
  | { ok: false; reason: 'no_secret' | 'no_signature' | 'bad_signature' };

export function verifyWhopSignature(
  rawBody: string,
  signatureHeader: string | null | undefined,
  secret: string | undefined,
): VerifyResult {
  if (!secret) return { ok: false, reason: 'no_secret' };
  if (!signatureHeader) return { ok: false, reason: 'no_signature' };

  const provided = signatureHeader.trim().toLowerCase();
  // Strip optional `sha256=` prefix some senders include
  const cleaned = provided.startsWith('sha256=') ? provided.slice(7) : provided;

  const expected = crypto
    .createHmac('sha256', secret)
    .update(rawBody, 'utf8')
    .digest('hex');

  let providedBuf: Buffer;
  let expectedBuf: Buffer;
  try {
    providedBuf = Buffer.from(cleaned, 'hex');
    expectedBuf = Buffer.from(expected, 'hex');
  } catch {
    return { ok: false, reason: 'bad_signature' };
  }

  if (providedBuf.length !== expectedBuf.length) {
    return { ok: false, reason: 'bad_signature' };
  }

  try {
    const equal = crypto.timingSafeEqual(providedBuf, expectedBuf);
    return equal ? { ok: true } : { ok: false, reason: 'bad_signature' };
  } catch {
    return { ok: false, reason: 'bad_signature' };
  }
}
