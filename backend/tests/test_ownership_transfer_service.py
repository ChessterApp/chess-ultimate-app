"""Tests for ownership-transfer state machine (PRD §11.3 #3)."""

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from services import ownership_transfer as svc


# ─── In-memory fake DB ──────────────────────────────────────────────────────


class _FakeDB:
    """Mimic supabase-py for ownership_transfer + organization_members."""

    def __init__(self):
        self.organization_ownership_transfers: list[dict] = []
        self.organization_members: list[dict] = []
        self._next_id = 0

    def _new_id(self):
        self._next_id += 1
        return f'transfer-{self._next_id}'

    def table(self, name):
        rows = getattr(self, name)
        db = self

        class _Chain:
            def __init__(self):
                self._filters: list[tuple[str, object]] = []
                self._select_cols = None
                self._payload = None
                self._lt = None
                self._in = None
                self._op = None  # 'insert' | 'update' | 'upsert'
                self._upsert_conflict = None
                self._is_select = False
                self._is_single = False
                self._is_maybe_single = False

            def select(self, *a, **kw):
                self._select_cols = a
                self._op = 'select'
                self._is_select = True
                return self

            def eq(self, col, val):
                self._filters.append((col, val))
                return self

            def lt(self, col, val):
                self._lt = (col, val)
                return self

            def in_(self, col, vals):
                self._in = (col, list(vals))
                return self

            def order(self, *a, **kw):
                return self

            def single(self):
                self._is_single = True
                return self

            def maybe_single(self):
                self._is_maybe_single = True
                return self

            def insert(self, payload):
                self._op = 'insert'
                self._payload = payload
                return self

            def update(self, payload):
                self._op = 'update'
                self._payload = payload
                return self

            def upsert(self, payload, on_conflict=None):
                self._op = 'upsert'
                self._payload = payload
                self._upsert_conflict = on_conflict
                return self

            def execute(self):
                if self._op == 'select':
                    matches = [
                        r for r in rows
                        if all(r.get(c) == v for c, v in self._filters)
                    ]
                    if self._is_single or self._is_maybe_single:
                        return MagicMock(
                            data=matches[0] if matches else None,
                        )
                    return MagicMock(data=matches)
                if self._op == 'insert':
                    row = dict(self._payload)
                    row.setdefault('id', db._new_id())
                    rows.append(row)
                    return MagicMock(data=[row])
                if self._op == 'update':
                    touched = []
                    for r in rows:
                        if (
                            all(r.get(c) == v for c, v in self._filters)
                            and (self._lt is None or (
                                r.get(self._lt[0]) is not None
                                and r.get(self._lt[0]) < self._lt[1]
                            ))
                            and (self._in is None or (
                                r.get(self._in[0]) in self._in[1]
                            ))
                        ):
                            r.update(self._payload)
                            touched.append(r)
                    return MagicMock(data=touched)
                if self._op == 'upsert':
                    conflict_cols = (
                        [c.strip() for c in (self._upsert_conflict or '').split(',')]
                        if self._upsert_conflict else []
                    )
                    payload = self._payload
                    if conflict_cols and all(c for c in conflict_cols):
                        for r in rows:
                            if all(r.get(c) == payload.get(c) for c in conflict_cols):
                                r.update(payload)
                                return MagicMock(data=[r])
                    row = dict(payload)
                    row.setdefault('id', db._new_id())
                    rows.append(row)
                    return MagicMock(data=[row])
                return MagicMock(data=[])

        return _Chain()


@pytest.fixture
def fake_db(monkeypatch):
    db = _FakeDB()
    # Seed: org has an owner row
    db.organization_members.append({
        'organization_id': 'org-1', 'user_id': 'owner-uid', 'role': 'owner',
    })
    monkeypatch.setattr(svc, '_get_supabase', lambda: db)
    return db


# ─── State machine coverage ─────────────────────────────────────────────────


class TestCreateTransfer:
    def test_happy_path_creates_invite_pending(self, fake_db):
        row = svc.create_transfer('org-1', 'owner-uid', 'assistant@x.com')
        assert row['state'] == 'invite_pending'
        assert row['token']
        assert row['invitee_email'] == 'assistant@x.com'
        assert len(fake_db.organization_ownership_transfers) == 1

    def test_email_lowercased(self, fake_db):
        row = svc.create_transfer('org-1', 'owner-uid', 'ASSISTANT@X.COM')
        assert row['invitee_email'] == 'assistant@x.com'

    def test_invalid_email_rejected(self, fake_db):
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.create_transfer('org-1', 'owner-uid', 'not-an-email')
        assert exc.value.code == 'invalid_input'

    def test_empty_owner_rejected(self, fake_db):
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.create_transfer('org-1', '', 'a@b.com')
        assert exc.value.code == 'invalid_input'

    def test_zero_ttl_rejected(self, fake_db):
        with pytest.raises(svc.OwnershipTransferError):
            svc.create_transfer('org-1', 'owner-uid', 'a@b.com', ttl_hours=0)

    def test_expires_at_is_in_the_future(self, fake_db):
        row = svc.create_transfer(
            'org-1', 'owner-uid', 'a@b.com', ttl_hours=48,
        )
        expires = datetime.fromisoformat(row['expires_at'])
        delta = expires - datetime.now(timezone.utc)
        # Between 47.5h and 48.5h
        assert timedelta(hours=47, minutes=30) < delta < timedelta(hours=48, minutes=30)


class TestAccept:
    def test_invite_pending_to_accepted(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        accepted = svc.accept_transfer(created['token'], 'invitee-uid')
        assert accepted['state'] == 'accepted'
        assert accepted['invitee_user_id'] == 'invitee-uid'
        assert accepted['accepted_at'] is not None

    def test_unknown_token_404(self, fake_db):
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.accept_transfer('bad-token', 'uid')
        assert exc.value.code == 'not_found'

    def test_already_accepted_409(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        svc.accept_transfer(created['token'], 'invitee-uid')
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.accept_transfer(created['token'], 'invitee-uid')
        assert exc.value.code == 'invalid_state'

    def test_expired_token_410(self, fake_db, monkeypatch):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com', ttl_hours=1)
        # Move expires_at into the past
        created_row = fake_db.organization_ownership_transfers[0]
        created_row['expires_at'] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.accept_transfer(created['token'], 'uid')
        assert exc.value.code == 'expired'
        # And the row state was bumped to expired
        assert created_row['state'] == 'expired'

    def test_missing_invitee_uid_400(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.accept_transfer(created['token'], '')
        assert exc.value.code == 'invalid_input'


class TestRevoke:
    def test_revoke_invite_pending(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        revoked = svc.revoke_transfer(created['id'], 'owner-uid')
        assert revoked['state'] == 'revoked'
        assert revoked['revoked_at'] is not None

    def test_revoke_accepted_works(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        svc.accept_transfer(created['token'], 'invitee-uid')
        revoked = svc.revoke_transfer(created['id'], 'owner-uid')
        assert revoked['state'] == 'revoked'

    def test_revoke_completed_rejected(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        svc.accept_transfer(created['token'], 'invitee-uid')
        svc.confirm_transfer(created['id'], 'owner-uid')
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.revoke_transfer(created['id'], 'owner-uid')
        assert exc.value.code == 'invalid_state'

    def test_revoke_by_non_owner_forbidden(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.revoke_transfer(created['id'], 'someone-else')
        assert exc.value.code == 'forbidden'

    def test_revoke_unknown_id_404(self, fake_db):
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.revoke_transfer('nonexistent', 'owner-uid')
        assert exc.value.code == 'not_found'


class TestConfirm:
    def test_confirm_accepted_swaps_roles(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        svc.accept_transfer(created['token'], 'invitee-uid')
        completed = svc.confirm_transfer(created['id'], 'owner-uid')
        assert completed['state'] == 'completed'
        assert completed['completed_at'] is not None
        # Membership rows updated
        members = {
            (m['user_id'], m['role'])
            for m in fake_db.organization_members
        }
        assert ('owner-uid', 'admin') in members
        assert ('invitee-uid', 'owner') in members

    def test_confirm_invite_pending_rejected(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.confirm_transfer(created['id'], 'owner-uid')
        assert exc.value.code == 'invalid_state'

    def test_confirm_by_non_owner_forbidden(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        svc.accept_transfer(created['token'], 'invitee-uid')
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.confirm_transfer(created['id'], 'someone-else')
        assert exc.value.code == 'forbidden'

    def test_confirm_expired_returns_410(self, fake_db):
        created = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        svc.accept_transfer(created['token'], 'invitee-uid')
        # Force-expire AFTER accept
        fake_db.organization_ownership_transfers[0]['expires_at'] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.confirm_transfer(created['id'], 'owner-uid')
        assert exc.value.code == 'expired'


class TestExpireDue:
    def test_expire_due_marks_old_invite_pending(self, fake_db):
        # Add a few rows manually
        now = datetime.now(timezone.utc)
        fake_db.organization_ownership_transfers.extend([
            {
                'id': 't1', 'organization_id': 'org-1',
                'state': 'invite_pending',
                'expires_at': (now - timedelta(hours=1)).isoformat(),
            },
            {
                'id': 't2', 'organization_id': 'org-1',
                'state': 'invite_pending',
                'expires_at': (now + timedelta(hours=10)).isoformat(),
            },
            {
                'id': 't3', 'organization_id': 'org-1',
                'state': 'completed',
                'expires_at': (now - timedelta(hours=10)).isoformat(),
            },
        ])
        n = svc.expire_due()
        assert n == 1
        assert fake_db.organization_ownership_transfers[0]['state'] == 'expired'
        # Non-pending stays untouched
        assert fake_db.organization_ownership_transfers[2]['state'] == 'completed'


class TestFullStateMachine:
    def test_invite_pending_then_accepted_then_revoked(self, fake_db):
        c = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        a = svc.accept_transfer(c['token'], 'invitee-uid')
        assert a['state'] == 'accepted'
        r = svc.revoke_transfer(c['id'], 'owner-uid')
        assert r['state'] == 'revoked'

    def test_invite_pending_then_expired(self, fake_db):
        c = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        # Force expire
        fake_db.organization_ownership_transfers[0]['expires_at'] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        n = svc.expire_due()
        assert n == 1

    def test_full_happy_path(self, fake_db):
        """Full state-machine traversal: invite_pending → accepted → completed.

        PRD §11.3 gate: state-machine test covering all 4 states.
        """
        c = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        assert c['state'] == 'invite_pending'
        a = svc.accept_transfer(c['token'], 'invitee-uid')
        assert a['state'] == 'accepted'
        done = svc.confirm_transfer(c['id'], 'owner-uid')
        assert done['state'] == 'completed'
        # Role swap happened
        members_by_uid = {m['user_id']: m['role'] for m in fake_db.organization_members}
        assert members_by_uid['owner-uid'] == 'admin'
        assert members_by_uid['invitee-uid'] == 'owner'

    def test_all_four_states_reachable(self, fake_db):
        """Each non-completed state is reachable from invite_pending."""
        # invite_pending
        c = svc.create_transfer('org-1', 'owner-uid', 'a@b.com')
        assert c['state'] == 'invite_pending'
        # accepted
        c2 = svc.create_transfer('org-1', 'owner-uid', 'b@b.com')
        accepted = svc.accept_transfer(c2['token'], 'u2')
        assert accepted['state'] == 'accepted'
        # revoked
        c3 = svc.create_transfer('org-1', 'owner-uid', 'c@b.com')
        revoked = svc.revoke_transfer(c3['id'], 'owner-uid')
        assert revoked['state'] == 'revoked'
        # expired
        c4 = svc.create_transfer('org-1', 'owner-uid', 'd@b.com')
        fake_db.organization_ownership_transfers[-1]['expires_at'] = (
            datetime.now(timezone.utc) - timedelta(hours=1)
        ).isoformat()
        with pytest.raises(svc.OwnershipTransferError) as exc:
            svc.accept_transfer(c4['token'], 'u4')
        assert exc.value.code == 'expired'
        # All four states present
        states = {r['state'] for r in fake_db.organization_ownership_transfers}
        assert {'invite_pending', 'accepted', 'revoked', 'expired'} <= states
