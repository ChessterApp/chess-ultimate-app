import { describe, it, expect, vi } from 'vitest';
import {
  extractAmountCents,
  extractEventId,
  extractOrgId,
  isRefundEvent,
  processRefundPayload,
} from '../refunds';

const REFUND_PAYLOAD = {
  action: 'refund.created',
  id: 'evt_refund_xyz_001',
  data: {
    id: 'ref_aaa',
    membership_id: 'mem_bbb',
    amount_cents: 12900,
    currency: 'USD',
    reason: 'requested_by_customer',
    metadata: {
      org_id: 'org-1234',
      kind: 'org_subscription',
    },
  },
};

describe('isRefundEvent', () => {
  it('matches refund.* events', () => {
    expect(isRefundEvent('refund.created')).toBe(true);
    expect(isRefundEvent('refund.updated')).toBe(true);
  });
  it('matches payment.refunded', () => {
    expect(isRefundEvent('payment.refunded')).toBe(true);
  });
  it('rejects subscription events', () => {
    expect(isRefundEvent('subscription.updated')).toBe(false);
    expect(isRefundEvent('membership.went_valid')).toBe(false);
  });
  it('rejects null/empty', () => {
    expect(isRefundEvent(null)).toBe(false);
    expect(isRefundEvent('')).toBe(false);
    expect(isRefundEvent(undefined)).toBe(false);
  });
});

describe('extractEventId', () => {
  it('reads top-level id', () => {
    expect(extractEventId(REFUND_PAYLOAD)).toBe('evt_refund_xyz_001');
  });
  it('prefers explicit event_id', () => {
    expect(extractEventId({ id: 'fallback', event_id: 'real' })).toBe('real');
  });
  it('returns null for missing', () => {
    expect(extractEventId({})).toBeNull();
    expect(extractEventId({ data: {} })).toBeNull();
  });
});

describe('extractOrgId', () => {
  it('reads data.metadata.org_id', () => {
    expect(extractOrgId(REFUND_PAYLOAD)).toBe('org-1234');
  });
  it('falls back to top-level metadata.organization_id', () => {
    expect(extractOrgId({ metadata: { organization_id: 'top' } })).toBe('top');
  });
  it('returns null when missing', () => {
    expect(extractOrgId({})).toBeNull();
  });
});

describe('extractAmountCents', () => {
  it('reads amount_cents directly', () => {
    expect(extractAmountCents(REFUND_PAYLOAD)).toBe(12900);
  });
  it('coerces string amount_cents', () => {
    expect(extractAmountCents({ data: { amount_cents: '49900' } })).toBe(49900);
  });
  it('falls back to dollars × 100', () => {
    expect(extractAmountCents({ data: { amount: 12.5 } })).toBe(1250);
  });
  it('defaults to 0', () => {
    expect(extractAmountCents({})).toBe(0);
  });
});

describe('processRefundPayload — idempotency', () => {
  function makeClient() {
    const refunds: Array<Record<string, unknown>> = [];
    const audits: Array<Record<string, unknown>> = [];
    const billing: Array<Record<string, unknown>> = [];
    return {
      refunds,
      audits,
      billing,
      selectExisting: vi.fn(async (eventId: string) => {
        const m = refunds.find((r) => r.whop_event_id === eventId);
        return m
          ? {
              id: 'rid',
              organization_id: m.organization_id as string,
              amount_cents: m.amount_cents as number,
            }
          : null;
      }),
      insertRefund: vi.fn(async (row: Record<string, unknown>) => {
        refunds.push(row);
      }),
      insertAudit: vi.fn(async (row: Record<string, unknown>) => {
        audits.push(row);
      }),
      stampBilling: vi.fn(async (orgId: string, amount: number, ts: string) => {
        billing.push({ organization_id: orgId, last_refund_amount_cents: amount, last_refund_at: ts });
      }),
    };
  }

  it('writes one row on first run', async () => {
    const c = makeClient();
    const res = await processRefundPayload(REFUND_PAYLOAD, c);
    expect(res.status).toBe('processed');
    expect(c.refunds).toHaveLength(1);
    expect(c.audits).toHaveLength(1);
    expect(c.billing).toHaveLength(1);
  });

  it('replay twice → 1 DB write (PRD §11.3 gate)', async () => {
    const c = makeClient();
    const first = await processRefundPayload(REFUND_PAYLOAD, c);
    const second = await processRefundPayload(REFUND_PAYLOAD, c);
    expect(first.status).toBe('processed');
    expect(second.status).toBe('already_processed');
    expect(c.refunds).toHaveLength(1);
    expect(c.audits).toHaveLength(1);
    expect(c.insertRefund).toHaveBeenCalledTimes(1);
    expect(c.insertAudit).toHaveBeenCalledTimes(1);
  });

  it('replay three times still one row', async () => {
    const c = makeClient();
    await processRefundPayload(REFUND_PAYLOAD, c);
    await processRefundPayload(REFUND_PAYLOAD, c);
    await processRefundPayload(REFUND_PAYLOAD, c);
    expect(c.refunds).toHaveLength(1);
  });

  it('skips when event id missing', async () => {
    const c = makeClient();
    const res = await processRefundPayload({ action: 'refund.created' }, c);
    expect(res.status).toBe('skipped');
    expect(c.refunds).toHaveLength(0);
    expect(c.insertRefund).not.toHaveBeenCalled();
  });

  it('skips when org id missing (but event id present)', async () => {
    const c = makeClient();
    const res = await processRefundPayload(
      { id: 'evt_noorg', data: { amount_cents: 100 } },
      c,
    );
    expect(res.status).toBe('skipped');
    if (res.status === 'skipped') {
      expect(res.reason).toBe('missing_org_id');
    }
    expect(c.refunds).toHaveLength(0);
  });

  it('different event ids create two rows', async () => {
    const c = makeClient();
    await processRefundPayload(REFUND_PAYLOAD, c);
    await processRefundPayload({ ...REFUND_PAYLOAD, id: 'evt_other' }, c);
    expect(c.refunds).toHaveLength(2);
  });

  it('stores currency lowercased', async () => {
    const c = makeClient();
    await processRefundPayload(REFUND_PAYLOAD, c);
    expect(c.refunds[0].currency).toBe('usd');
  });

  it('preserves raw payload for audit trail', async () => {
    const c = makeClient();
    await processRefundPayload(REFUND_PAYLOAD, c);
    expect(c.refunds[0].raw_payload).toEqual(REFUND_PAYLOAD);
  });
});
