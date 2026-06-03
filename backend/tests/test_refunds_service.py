"""Tests for refunds service — idempotency + extraction (PRD §11.3 #4)."""

from unittest.mock import MagicMock, patch

import pytest

from services import refunds as svc


# ─── Sample payload (matches Whop's refund webhook shape) ───────────────────

REFUND_PAYLOAD = {
    'action': 'refund.created',
    'id': 'evt_refund_xyz_001',
    'data': {
        'id': 'ref_aaa',
        'membership_id': 'mem_bbb',
        'amount_cents': 12900,
        'currency': 'USD',
        'reason': 'requested_by_customer',
        'metadata': {
            'org_id': 'org-1234',
            'kind': 'org_subscription',
        },
    },
}


class TestEventClassification:
    def test_is_refund_event_for_refund_created(self):
        assert svc.is_refund_event('refund.created') is True

    def test_is_refund_event_for_refund_updated(self):
        assert svc.is_refund_event('refund.updated') is True

    def test_is_refund_event_for_payment_refunded(self):
        assert svc.is_refund_event('payment.refunded') is True

    def test_is_refund_event_false_for_subscription(self):
        assert svc.is_refund_event('subscription.updated') is False
        assert svc.is_refund_event('subscription.canceled') is False
        assert svc.is_refund_event('membership.went_valid') is False

    def test_is_refund_event_false_for_none(self):
        assert svc.is_refund_event(None) is False
        assert svc.is_refund_event('') is False


class TestExtractors:
    def test_extract_event_id_from_top_level(self):
        assert svc._extract_event_id(REFUND_PAYLOAD) == 'evt_refund_xyz_001'

    def test_extract_event_id_prefers_explicit_event_id_field(self):
        payload = {'id': 'fallback', 'event_id': 'evt_real'}
        assert svc._extract_event_id(payload) == 'evt_real'

    def test_extract_event_id_returns_none_when_missing(self):
        assert svc._extract_event_id({}) is None
        assert svc._extract_event_id({'data': {}}) is None

    def test_extract_org_id_from_metadata(self):
        assert svc._extract_org_id(REFUND_PAYLOAD) == 'org-1234'

    def test_extract_org_id_falls_back_to_top_level_metadata(self):
        payload = {'metadata': {'organization_id': 'org-fallback'}}
        assert svc._extract_org_id(payload) == 'org-fallback'

    def test_extract_org_id_returns_none_when_missing(self):
        assert svc._extract_org_id({}) is None
        assert svc._extract_org_id({'data': {'metadata': {}}}) is None

    def test_extract_amount_from_amount_cents(self):
        assert svc._extract_amount_cents(REFUND_PAYLOAD) == 12900

    def test_extract_amount_from_string(self):
        payload = {'data': {'amount_cents': '49900'}}
        assert svc._extract_amount_cents(payload) == 49900

    def test_extract_amount_falls_back_to_dollars(self):
        payload = {'data': {'amount': 12.5}}
        assert svc._extract_amount_cents(payload) == 1250

    def test_extract_amount_zero_default(self):
        assert svc._extract_amount_cents({'data': {}}) == 0
        assert svc._extract_amount_cents({}) == 0


# ─── Idempotency ─────────────────────────────────────────────────────────────

class _FakeSupabase:
    """In-memory fake that mimics the subset of supabase-py we use.

    Tables tracked:
      * organization_refunds: dedupes on whop_event_id
      * organization_billing_audit: dedupes on (event_kind, event_source_id)
      * organization_billing: upsert keyed by organization_id
    """

    def __init__(self):
        self.organization_refunds: list[dict] = []
        self.organization_billing_audit: list[dict] = []
        self.organization_billing: list[dict] = []

    def table(self, name):
        rows = getattr(self, name, None)
        if rows is None:
            rows = []
            setattr(self, name, rows)

        class _Chain:
            def __init__(inner):
                inner._filters: list[tuple[str, object]] = []
                inner._select_cols = None
                inner._upsert_payload = None
                inner._upsert_on_conflict = None
                inner._upsert_ignore = False
                inner._is_select = False
                inner._is_maybe_single = False

            def select(inner, cols, *args, **kw):
                inner._select_cols = cols
                inner._is_select = True
                return inner

            def eq(inner, col, val):
                inner._filters.append((col, val))
                return inner

            def single(inner):
                return inner

            def maybe_single(inner):
                inner._is_maybe_single = True
                return inner

            def order(inner, *_a, **_kw):
                return inner

            def limit(inner, *_a, **_kw):
                return inner

            def upsert(inner, payload, on_conflict=None, ignore_duplicates=False):
                inner._upsert_payload = payload
                inner._upsert_on_conflict = on_conflict
                inner._upsert_ignore = ignore_duplicates
                return inner

            def execute(inner):
                if inner._is_select:
                    matches = [
                        r for r in rows
                        if all(r.get(c) == v for c, v in inner._filters)
                    ]
                    if inner._is_maybe_single:
                        return MagicMock(data=matches[0] if matches else None)
                    return MagicMock(data=matches)
                if inner._upsert_payload is not None:
                    payload = inner._upsert_payload
                    conflict_cols = (
                        [c.strip() for c in (inner._upsert_on_conflict or '').split(',')]
                        if inner._upsert_on_conflict else []
                    )
                    if conflict_cols and all(c for c in conflict_cols):
                        # Find existing conflicting row
                        for i, existing in enumerate(rows):
                            if all(existing.get(c) == payload.get(c) for c in conflict_cols):
                                if inner._upsert_ignore:
                                    return MagicMock(data=[existing])
                                rows[i] = {**existing, **payload}
                                return MagicMock(data=[rows[i]])
                    rows.append(dict(payload))
                    return MagicMock(data=[rows[-1]])
                return MagicMock(data=[])

        return _Chain()


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeSupabase()
    monkeypatch.setattr(svc, '_get_supabase', lambda: db)
    return db


class TestProcessRefundEvent:
    def test_happy_path_writes_one_row(self, fake_db):
        result = svc.process_refund_event(REFUND_PAYLOAD)
        assert result['status'] == 'processed'
        assert result['org_id'] == 'org-1234'
        assert result['amount_cents'] == 12900
        assert len(fake_db.organization_refunds) == 1
        assert fake_db.organization_refunds[0]['whop_event_id'] == 'evt_refund_xyz_001'

    def test_replay_same_event_does_not_double_write(self, fake_db):
        """Idempotency gate (PRD §11.3): replay webhook twice → 1 DB write."""
        first = svc.process_refund_event(REFUND_PAYLOAD)
        second = svc.process_refund_event(REFUND_PAYLOAD)
        assert first['status'] == 'processed'
        assert second['status'] == 'already_processed'
        assert len(fake_db.organization_refunds) == 1, (
            f'expected exactly 1 refund row, got {fake_db.organization_refunds}'
        )

    def test_replay_three_times_still_one_row(self, fake_db):
        for _ in range(3):
            svc.process_refund_event(REFUND_PAYLOAD)
        assert len(fake_db.organization_refunds) == 1

    def test_audit_log_also_idempotent(self, fake_db):
        svc.process_refund_event(REFUND_PAYLOAD)
        svc.process_refund_event(REFUND_PAYLOAD)
        assert len(fake_db.organization_billing_audit) == 1
        assert fake_db.organization_billing_audit[0]['event_kind'] == 'refund'
        assert fake_db.organization_billing_audit[0]['event_source_id'] == 'evt_refund_xyz_001'

    def test_billing_row_gets_last_refund_stamp(self, fake_db):
        svc.process_refund_event(REFUND_PAYLOAD)
        assert len(fake_db.organization_billing) == 1
        billing = fake_db.organization_billing[0]
        assert billing['organization_id'] == 'org-1234'
        assert billing['last_refund_amount_cents'] == 12900
        assert 'last_refund_at' in billing

    def test_skips_when_no_event_id(self, fake_db):
        result = svc.process_refund_event({'action': 'refund.created', 'data': {}})
        assert result['status'] == 'skipped'
        assert result['reason'] == 'missing_event_id'
        assert fake_db.organization_refunds == []

    def test_skips_when_no_org_id(self, fake_db):
        payload = {
            'id': 'evt_no_org',
            'action': 'refund.created',
            'data': {'amount_cents': 100},
        }
        result = svc.process_refund_event(payload)
        assert result['status'] == 'skipped'
        assert result['reason'] == 'missing_org_id'
        assert fake_db.organization_refunds == []

    def test_different_event_ids_create_different_rows(self, fake_db):
        first = dict(REFUND_PAYLOAD)
        second = dict(REFUND_PAYLOAD, id='evt_refund_xyz_002')
        svc.process_refund_event(first)
        svc.process_refund_event(second)
        assert len(fake_db.organization_refunds) == 2

    def test_stores_raw_payload_for_audit_trail(self, fake_db):
        svc.process_refund_event(REFUND_PAYLOAD)
        row = fake_db.organization_refunds[0]
        assert row['raw_payload'] == REFUND_PAYLOAD

    def test_stores_currency_lowercased(self, fake_db):
        svc.process_refund_event(REFUND_PAYLOAD)
        assert fake_db.organization_refunds[0]['currency'] == 'usd'
