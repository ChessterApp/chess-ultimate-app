/**
 * Refund helpers — shared by the Whop webhook handler and tests.
 *
 * Idempotency contract (PRD §11.3 #4): given a refund webhook payload with
 * `event_id` X, processing it any number of times must result in:
 *   - exactly one row in `organization_refunds` keyed by X
 *   - exactly one row in `organization_billing_audit` keyed (refund, X)
 *
 * Pure helpers (`isRefundEvent`, `extractEventId`, `extractOrgId`,
 * `extractAmountCents`) are exported for unit tests without DB access.
 */

const REFUND_EVENT_PREFIXES = ['refund.', 'payment.refunded'];

export function isRefundEvent(name: string | null | undefined): boolean {
  if (!name) return false;
  return REFUND_EVENT_PREFIXES.some((p) => name.startsWith(p));
}

export function extractEventId(payload: Record<string, unknown>): string | null {
  if (!payload || typeof payload !== 'object') return null;
  const candidates = [
    payload.event_id,
    payload.id,
    ((payload.data as Record<string, unknown>) || {}).event_id,
  ];
  for (const c of candidates) {
    if (typeof c === 'string' && c.trim()) return c.trim();
  }
  return null;
}

export function extractOrgId(payload: Record<string, unknown>): string | null {
  const data = (payload.data as Record<string, unknown>) || {};
  const dataMeta = (data.metadata as Record<string, unknown>) || {};
  for (const key of ['org_id', 'organization_id']) {
    const v = dataMeta[key];
    if (typeof v === 'string' && v) return v;
  }
  const topMeta = (payload.metadata as Record<string, unknown>) || {};
  for (const key of ['org_id', 'organization_id']) {
    const v = topMeta[key];
    if (typeof v === 'string' && v) return v;
  }
  return null;
}

export function extractAmountCents(payload: Record<string, unknown>): number {
  const data = (payload.data as Record<string, unknown>) || {};
  for (const key of [
    'amount_cents',
    'refund_amount_cents',
    'amount_refunded_cents',
    'amount_refunded',
  ]) {
    const raw = data[key];
    if (typeof raw === 'number' && Number.isFinite(raw)) return raw;
    if (typeof raw === 'string') {
      const n = Number(raw);
      if (Number.isFinite(n)) return n;
    }
  }
  const dollars = data.amount;
  if (typeof dollars === 'number' && Number.isFinite(dollars)) {
    return Math.round(dollars * 100);
  }
  return 0;
}

export type RefundResult =
  | {
      status: 'processed' | 'already_processed';
      event_id: string;
      org_id: string;
      amount_cents: number;
    }
  | {
      status: 'skipped';
      reason: 'missing_event_id' | 'missing_org_id';
      event_id: string | null;
      org_id: string | null;
      amount_cents: number;
    };

interface RefundsClient {
  // Minimal surface the webhook needs from supabase-admin.
  selectExisting(eventId: string): Promise<{ id: string; organization_id: string; amount_cents: number } | null>;
  insertRefund(row: Record<string, unknown>): Promise<void>;
  insertAudit(row: Record<string, unknown>): Promise<void>;
  stampBilling(orgId: string, amountCents: number, timestamp: string): Promise<void>;
}

export async function processRefundPayload(
  payload: Record<string, unknown>,
  client: RefundsClient,
): Promise<RefundResult> {
  const eventId = extractEventId(payload);
  if (!eventId) {
    return {
      status: 'skipped',
      reason: 'missing_event_id',
      event_id: null,
      org_id: null,
      amount_cents: 0,
    };
  }
  const orgId = extractOrgId(payload);
  const amountCents = extractAmountCents(payload);

  const existing = await client.selectExisting(eventId);
  if (existing) {
    return {
      status: 'already_processed',
      event_id: eventId,
      org_id: existing.organization_id || orgId || '',
      amount_cents: existing.amount_cents ?? amountCents,
    };
  }
  if (!orgId) {
    return {
      status: 'skipped',
      reason: 'missing_org_id',
      event_id: eventId,
      org_id: null,
      amount_cents: amountCents,
    };
  }

  const data = (payload.data as Record<string, unknown>) || {};
  const membershipId =
    (data.membership_id as string | undefined) ||
    (data.whop_membership_id as string | undefined) ||
    null;
  const currency = ((data.currency as string) || 'usd').toLowerCase();
  const reason = (data.reason as string | undefined) || null;

  await client.insertRefund({
    organization_id: orgId,
    whop_event_id: eventId,
    whop_membership_id: membershipId,
    amount_cents: amountCents,
    currency,
    reason,
    status: 'processed',
    raw_payload: payload,
  });
  await client.insertAudit({
    organization_id: orgId,
    event_kind: 'refund',
    event_source_id: eventId,
    payload: {
      amount_cents: amountCents,
      currency,
      reason,
      membership_id: membershipId,
    },
  });
  await client.stampBilling(orgId, amountCents, new Date().toISOString());

  return {
    status: 'processed',
    event_id: eventId,
    org_id: orgId,
    amount_cents: amountCents,
  };
}
