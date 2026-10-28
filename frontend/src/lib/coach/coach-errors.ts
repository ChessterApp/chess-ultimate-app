/**
 * Hermes's failures, read once and shown in the student's language. The proxies passed «Hermes error: 429»
 * or «HTTP 500» into the chat, and the game actions dropped Hermes's reason (seam audit 28.10). Server side:
 * `hermesErrorFrame` / `unreachableFrame` build the SSE error frame; client side: `coachErrorText`.
 */

export type CoachErrorCode =
  | 'rate_limited'
  | 'engine_unavailable'
  | 'not_found'
  | 'game_over'
  | 'nothing_to_take_back'
  | 'not_your_move'
  | 'unreachable'
  | 'server'
  | 'rejected';

export interface CoachErrorFrame {
  error: string;
  error_code: CoachErrorCode;
  rate_limited?: true;
  retry_after?: number;
}

const CODES: ReadonlySet<string> = new Set<CoachErrorCode>([
  'rate_limited', 'engine_unavailable', 'not_found', 'game_over', 'nothing_to_take_back', 'not_your_move',
  'unreachable', 'server', 'rejected',
]);

export function isCoachErrorCode(value: unknown): value is CoachErrorCode {
  return typeof value === 'string' && CODES.has(value);
}

/** Hermes's `detail` text and fields, through the proxy's `{ error, detail }` wrapper if there is one. */
function unwrap(body: unknown): { text: string; retryAfter?: number } {
  let d: unknown = body;
  // proxyToHermes: { error, detail: <Hermes body> }; Hermes: { detail: string | { message, retry_after } }
  for (let i = 0; i < 3 && d && typeof d === 'object' && 'detail' in (d as object); i++) {
    d = (d as { detail: unknown }).detail;
  }
  if (typeof d === 'string') return { text: d };
  if (d && typeof d === 'object') {
    const o = d as Record<string, unknown>;
    const text = (typeof o.message === 'string' && o.message) || (typeof o.error === 'string' && o.error) || '';
    return { text, retryAfter: typeof o.retry_after === 'number' ? o.retry_after : undefined };
  }
  if (body && typeof body === 'object' && typeof (body as { error?: unknown }).error === 'string') {
    return { text: (body as { error: string }).error };
  }
  return { text: '' };
}

/** What a failed Hermes answer (status + JSON body) means for the student. */
export function classifyHermesError(
  status: number,
  body: unknown,
): { code: CoachErrorCode; message: string; retryAfter?: number } {
  const { text, retryAfter } = unwrap(body);
  const message = text || `Hermes error: ${status}`;
  if (status === 429) return { code: 'rate_limited', message, ...(retryAfter !== undefined ? { retryAfter } : {}) };
  if (/engine is unavailable/i.test(text) || status === 503) return { code: 'engine_unavailable', message };
  if (/not found|not a game/i.test(text)) return { code: 'not_found', message };
  if (/game is over/i.test(text)) return { code: 'game_over', message };
  if (/nothing to take back/i.test(text)) return { code: 'nothing_to_take_back', message };
  if (/not your move/i.test(text)) return { code: 'not_your_move', message };
  // 0: no answer at all; 502/504: the proxy or the gateway could not reach Hermes
  if (status === 0 || status === 502 || status === 504) return { code: 'unreachable', message };
  if (status >= 400 && status < 500 && text) return { code: 'rejected', message };
  return { code: 'server', message };
}

/** The SSE error frame for a non-ok Hermes response (server side, in a proxy). */
export async function hermesErrorFrame(res: Response): Promise<CoachErrorFrame> {
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const c = classifyHermesError(res.status, body);
  return {
    error: c.message,
    error_code: c.code,
    ...(c.code === 'rate_limited' ? { rate_limited: true as const } : {}),
    ...(c.retryAfter !== undefined ? { retry_after: c.retryAfter } : {}),
  };
}

/** The SSE error frame for a Hermes the proxy could not reach (network error, timeout). */
export function unreachableFrame(err: unknown): CoachErrorFrame {
  return { error: err instanceof Error ? err.message : 'Hermes unreachable', error_code: 'unreachable' };
}

type Translate = (key: string, values?: Record<string, string | number>) => string;

const KEYS: Record<Exclude<CoachErrorCode, 'rate_limited' | 'rejected'>, string> = {
  engine_unavailable: 'errorEngineUnavailable',
  not_found: 'errorNotFound',
  game_over: 'errorGameOver',
  nothing_to_take_back: 'errorNothingToTakeBack',
  not_your_move: 'errorNotYourMove',
  unreachable: 'errorCoachUnreachable',
  server: 'errorServer',
};

/** The student-facing text for a coach failure, in the `coach` namespace's language. */
export function coachErrorText(
  t: Translate,
  code: CoachErrorCode,
  opts: { retryAfter?: number; detail?: string } = {},
): string {
  if (code === 'rate_limited') {
    const seconds = typeof opts.retryAfter === 'number' && opts.retryAfter > 0 ? Math.ceil(opts.retryAfter) : null;
    return seconds ? t('errorRateLimited', { seconds }) : t('errorRateLimitedNoTime');
  }
  // A refusal Hermes worded itself («e9 is not a legal move here.») is shown as it is, as the move error was.
  if (code === 'rejected') return opts.detail || t('errorServer');
  return t(KEYS[code]);
}

/**
 * An SSE error frame's text: the proxies tag their own failures with error_code (a 429, Hermes unreachable…) and
 * get worded here; Hermes's in-stream errors carry no code and are already worded for the student.
 */
export function frameErrorText(
  t: Translate,
  data: { error?: unknown; error_code?: unknown; retry_after?: unknown },
): string {
  if (!isCoachErrorCode(data.error_code)) return String(data.error);
  return coachErrorText(t, data.error_code, {
    retryAfter: typeof data.retry_after === 'number' ? data.retry_after : undefined,
    detail: typeof data.error === 'string' ? data.error : undefined,
  });
}
