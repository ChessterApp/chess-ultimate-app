/**
 * Invite-flow JWT (HS256).
 *
 * Phase 1 of the Chess Empire → Chesster onboarding arc. After a parent
 * passes the DOB gate (verify route), the server signs a short-lived JWT
 * containing the resolved student/branch context. The token is handed to
 * the Clerk sign-up page via `?invite=…`, and replayed back through the
 * Clerk webhook in Phase 2/3 to write the `external_student_id` linkage.
 *
 * Plumbed without a new dependency — `node:crypto` HMAC is sufficient for
 * HS256 and the JWT format is small. Mirrors the Python equivalent at
 * ``backend/services/invite_jwt.py`` which uses ``pyjwt``.
 *
 * Default TTL: 900 seconds (15 min). The webhook also enforces single-use
 * via a `consumed_at` write in Phase 2/3.
 */
import 'server-only';
import { createHmac, timingSafeEqual } from 'node:crypto';

export const INVITE_JWT_TTL_SECONDS = 15 * 60;

export interface InviteJwtPayload {
  /** Chess Empire student UUID. */
  student_id: string;
  /** Chess Empire branch UUID (mirrors the token's branch). */
  branch_id: string;
  /** Chesster `branch_invite_tokens.id` — used by the webhook for audit. */
  branch_token_id: string;
  /** Chesster `organizations.id`. */
  org_id: string;
}

interface InviteJwtClaims extends InviteJwtPayload {
  iat: number;
  exp: number;
}

export class InviteJwtError extends Error {
  constructor(message: string) {
    super(message);
    this.name = 'InviteJwtError';
  }
}

function getSecret(): string {
  const secret = process.env.INVITE_JWT_SECRET;
  if (!secret) {
    throw new InviteJwtError('INVITE_JWT_SECRET not configured');
  }
  return secret;
}

function b64urlEncode(buf: Buffer): string {
  return buf.toString('base64').replace(/=+$/, '').replace(/\+/g, '-').replace(/\//g, '_');
}

function b64urlDecode(str: string): Buffer {
  const pad = str.length % 4 === 0 ? '' : '='.repeat(4 - (str.length % 4));
  return Buffer.from(str.replace(/-/g, '+').replace(/_/g, '/') + pad, 'base64');
}

function sign(headerAndPayload: string, secret: string): string {
  return b64urlEncode(createHmac('sha256', secret).update(headerAndPayload).digest());
}

export function signInviteJwt(
  payload: InviteJwtPayload,
  ttlSeconds: number = INVITE_JWT_TTL_SECONDS,
  nowSeconds: number = Math.floor(Date.now() / 1000),
): string {
  const secret = getSecret();
  const header = { alg: 'HS256', typ: 'JWT' };
  const claims: InviteJwtClaims = {
    ...payload,
    iat: nowSeconds,
    exp: nowSeconds + ttlSeconds,
  };
  const encodedHeader = b64urlEncode(Buffer.from(JSON.stringify(header)));
  const encodedPayload = b64urlEncode(Buffer.from(JSON.stringify(claims)));
  const signingInput = `${encodedHeader}.${encodedPayload}`;
  return `${signingInput}.${sign(signingInput, secret)}`;
}

export function verifyInviteJwt(
  token: string,
  nowSeconds: number = Math.floor(Date.now() / 1000),
): InviteJwtClaims {
  const secret = getSecret();
  const parts = token.split('.');
  if (parts.length !== 3) {
    throw new InviteJwtError('Malformed token');
  }
  const [encodedHeader, encodedPayload, encodedSig] = parts;
  const expected = sign(`${encodedHeader}.${encodedPayload}`, secret);
  const expectedBuf = Buffer.from(expected);
  const sigBuf = Buffer.from(encodedSig);
  if (expectedBuf.length !== sigBuf.length || !timingSafeEqual(expectedBuf, sigBuf)) {
    throw new InviteJwtError('Bad signature');
  }
  let claims: InviteJwtClaims;
  try {
    claims = JSON.parse(b64urlDecode(encodedPayload).toString('utf8')) as InviteJwtClaims;
  } catch {
    throw new InviteJwtError('Malformed payload');
  }
  if (typeof claims.exp !== 'number' || claims.exp < nowSeconds) {
    throw new InviteJwtError('Token expired');
  }
  if (!claims.student_id || !claims.branch_id || !claims.branch_token_id || !claims.org_id) {
    throw new InviteJwtError('Missing required claim');
  }
  return claims;
}
