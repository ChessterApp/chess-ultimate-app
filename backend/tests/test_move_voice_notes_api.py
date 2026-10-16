"""
Tests for per-move voice notes (/api/games/<game_id>/voice-notes) in
api/user_databases.py, plus the cleanup paths that remove notes with their
game / database and the copy-to-workspace duplication.

Uses a small stateful in-memory Supabase fake (tables + storage bucket) so the
tests can assert what was written and removed. Auth is mocked to USER_A; the
stranger / viewer cases swap the decoded subject.
"""

import io
from datetime import datetime, timedelta, timezone

import pytest
from unittest.mock import patch

from api.user_databases import (
    DATABASES_TABLE,
    GAMES_TABLE,
    VOICE_NOTES_TABLE,
    VOICE_NOTES_BUCKET,
    VOICE_NOTE_MAX_BYTES,
)

USER_A = 'user_a'   # owner
USER_B = 'user_b'   # share-token viewer / stranger
TOKEN = 'share-tok-123'
GAME_ID = 'game-1'
DB_ID = 'db-1'


# ─── Stateful fake ────────────────────────────────────────────────────────────

class FakeResult:
    def __init__(self, data):
        self.data = data
        self.count = len(data)


class FakeQuery:
    def __init__(self, store, table):
        self._store = store
        self._table = table
        self._mode = 'select'
        self._payload = None
        self._filters = []

    def select(self, *a, **k):
        self._mode = 'select'
        return self

    def insert(self, data, **k):
        self._mode = 'insert'
        self._payload = data if isinstance(data, list) else [data]
        return self

    def update(self, data, **k):
        self._mode = 'update'
        self._payload = data
        return self

    def delete(self, **k):
        self._mode = 'delete'
        return self

    def eq(self, col, val):
        self._filters.append(lambda r: r.get(col) == val)
        return self

    def in_(self, col, vals):
        vals = set(vals)
        self._filters.append(lambda r: r.get(col) in vals)
        return self

    def is_(self, col, val):
        self._filters.append(lambda r: r.get(col) is None)
        return self

    @property
    def not_(self):
        return _NotNull(self)

    def lt(self, *a, **k):
        return self

    def ilike(self, *a, **k):
        return self

    def order(self, *a, **k):
        return self

    def execute(self):
        rows = self._store.setdefault(self._table, [])
        match = [r for r in rows if all(f(r) for f in self._filters)]
        if self._mode == 'insert':
            created = []
            for row in self._payload:
                row = {'id': row.get('id') or f'{self._table}-{len(rows) + 1}',
                       'created_at': '2026-10-16T10:00:00+00:00', **row}
                rows.append(row)
                created.append(dict(row))
            return FakeResult(created)
        if self._mode == 'update':
            for r in match:
                r.update(self._payload)
        if self._mode == 'delete':
            self._store[self._table] = [r for r in rows if r not in match]
        return FakeResult([dict(r) for r in match])


class FakeBucket:
    def __init__(self, storage):
        self._s = storage

    def upload(self, path, file, file_options=None):
        self._s['objects'][path] = file
        return {'path': path}

    def remove(self, paths):
        self._s['removed'].extend(paths)
        for p in paths:
            self._s['objects'].pop(p, None)
        return []

    def copy(self, from_path, to_path):
        self._s['objects'][to_path] = self._s['objects'][from_path]
        return {'path': to_path}

    def create_signed_url(self, path, expires_in):
        return {'signedURL': f'https://signed.example/{path}?ttl={expires_in}'}


class FakeStorage:
    def __init__(self, storage):
        self._s = storage

    def from_(self, bucket):
        assert bucket == VOICE_NOTES_BUCKET
        return FakeBucket(self._s)


class FakeSupabase:
    def __init__(self, store):
        self.store = store
        self.storage_state = {'objects': {}, 'removed': []}
        self.storage = FakeStorage(self.storage_state)

    def table(self, name):
        return FakeQuery(self.store, name)


def _note(idx, node_path, game_id=GAME_ID, owner=USER_A):
    path = f'{owner}/{game_id}/note{idx}.webm'
    return {
        'id': f'note-{idx}',
        'game_id': game_id,
        'owner_user_id': owner,
        'node_path': node_path,
        'storage_path': path,
        'mime_type': 'audio/webm',
        'duration_ms': 3000,
        'created_at': '2026-10-15T10:00:00+00:00',
    }


@pytest.fixture
def fake():
    sb = FakeSupabase({
        DATABASES_TABLE: [{
            'id': DB_ID, 'user_id': USER_A, 'name': 'Openings', 'is_default': False,
            'share_token': TOKEN, 'deleted_at': None,
        }],
        GAMES_TABLE: [{
            'id': GAME_ID, 'user_id': USER_A, 'database_id': DB_ID, 'pgn': '1. e4 e5 *',
            'deleted_at': None,
        }],
        VOICE_NOTES_TABLE: [_note(1, 'e4'), _note(2, 'e4 e5'), _note(3, 'e4 e5 Nf3'), _note(4, 'd4')],
    })
    for n in sb.store[VOICE_NOTES_TABLE]:
        sb.storage_state['objects'][n['storage_path']] = b'audio'
    with patch('api.user_databases.supabase', sb), patch('api.user_games.supabase', sb):
        yield sb


@pytest.fixture
def app():
    from flask import Flask
    from api.user_databases import user_databases_bp
    from api.user_games import user_games_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(user_databases_bp)
    test_app.register_blueprint(user_games_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


AUTH = {'Authorization': 'Bearer fake-jwt-token'}


@pytest.fixture
def as_user():
    """Context-manager factory: as_user(USER_B) decodes the JWT to that subject."""
    def _as(user_id):
        return patch('utils.auth._decode_clerk_token', return_value={'sub': user_id})
    return _as


@pytest.fixture(autouse=True)
def default_owner(as_user):
    with as_user(USER_A):
        yield


@pytest.fixture(autouse=True)
def mock_owner_name():
    with patch('api.user_databases._owner_display_name', return_value='Alice A'):
        yield


def _upload(client, node_path='e4 e5', mime='audio/webm;codecs=opus', size=1024, duration='4200', game_id=GAME_ID):
    data = {
        'node_path': node_path,
        'duration_ms': duration,
        'file': (io.BytesIO(b'a' * size), 'note.webm', mime),
    }
    return client.post(f'/api/games/{game_id}/voice-notes', headers=AUTH, data=data,
                       content_type='multipart/form-data')


# ─── List ────────────────────────────────────────────────────────────────────

class TestListVoiceNotes:
    def test_owner_lists_without_storage_keys(self, client, fake):
        resp = client.get(f'/api/games/{GAME_ID}/voice-notes', headers=AUTH)
        assert resp.status_code == 200
        notes = resp.get_json()
        assert [n['node_path'] for n in notes] == ['e4', 'e4 e5', 'e4 e5 Nf3', 'd4']
        assert all('storage_path' not in n and 'owner_user_id' not in n for n in notes)

    def test_share_token_viewer_can_list(self, client, fake, as_user):
        with as_user(USER_B):
            resp = client.get(f'/api/games/{GAME_ID}/voice-notes?share_token={TOKEN}', headers=AUTH)
        assert resp.status_code == 200
        assert len(resp.get_json()) == 4

    def test_stranger_gets_404(self, client, fake, as_user):
        with as_user(USER_B):
            resp = client.get(f'/api/games/{GAME_ID}/voice-notes', headers=AUTH)
        assert resp.status_code == 404

    def test_wrong_or_revoked_token_gets_404(self, client, fake, as_user):
        with as_user(USER_B):
            assert client.get(f'/api/games/{GAME_ID}/voice-notes?share_token=nope', headers=AUTH).status_code == 404
            fake.store[DATABASES_TABLE][0]['share_token'] = None
            assert client.get(f'/api/games/{GAME_ID}/voice-notes?share_token={TOKEN}', headers=AUTH).status_code == 404

    def test_token_for_other_database_gets_404(self, client, fake, as_user):
        fake.store[GAMES_TABLE][0]['database_id'] = 'db-other'
        with as_user(USER_B):
            resp = client.get(f'/api/games/{GAME_ID}/voice-notes?share_token={TOKEN}', headers=AUTH)
        assert resp.status_code == 404

    def test_requires_auth(self, client):
        assert client.get(f'/api/games/{GAME_ID}/voice-notes').status_code == 401


# ─── Upload ──────────────────────────────────────────────────────────────────

class TestUploadVoiceNote:
    def test_owner_upload_stores_object_under_owner_and_game(self, client, fake):
        fake.store[VOICE_NOTES_TABLE] = []
        resp = _upload(client, node_path='e4 e5')
        assert resp.status_code == 201
        body = resp.get_json()
        assert body['node_path'] == 'e4 e5'
        assert body['mime_type'] == 'audio/webm'
        assert body['duration_ms'] == 4200
        assert 'storage_path' not in body

        [row] = fake.store[VOICE_NOTES_TABLE]
        assert row['owner_user_id'] == USER_A
        assert row['storage_path'].startswith(f'{USER_A}/{GAME_ID}/')
        assert row['storage_path'].endswith('.webm')
        assert row['storage_path'] in fake.storage_state['objects']

    def test_ios_mp4_gets_m4a_extension(self, client, fake):
        resp = _upload(client, mime='audio/mp4')
        assert resp.status_code == 201
        new = [r for r in fake.store[VOICE_NOTES_TABLE] if r['id'] == resp.get_json()['id']][0]
        assert new['storage_path'].endswith('.m4a')

    def test_rerecord_replaces_old_note_and_object(self, client, fake):
        old_path = _note(2, 'e4 e5')['storage_path']
        resp = _upload(client, node_path='e4 e5')
        assert resp.status_code == 201
        at_move = [r for r in fake.store[VOICE_NOTES_TABLE] if r['node_path'] == 'e4 e5']
        assert len(at_move) == 1 and at_move[0]['id'] == resp.get_json()['id']
        assert old_path in fake.storage_state['removed']

    def test_viewer_with_token_cannot_upload(self, client, fake, as_user):
        with as_user(USER_B):
            data = {'node_path': 'e4', 'duration_ms': '1000',
                    'file': (io.BytesIO(b'a'), 'n.webm', 'audio/webm')}
            resp = client.post(f'/api/games/{GAME_ID}/voice-notes?share_token={TOKEN}', headers=AUTH,
                               data=data, content_type='multipart/form-data')
        assert resp.status_code == 404
        assert len(fake.store[VOICE_NOTES_TABLE]) == 4

    def test_stranger_cannot_upload(self, client, fake, as_user):
        with as_user(USER_B):
            assert _upload(client).status_code == 404

    def test_rejects_non_audio(self, client, fake):
        assert _upload(client, mime='video/webm').status_code == 415
        assert _upload(client, mime='text/plain').status_code == 415

    def test_rejects_over_5mb(self, client, fake):
        assert _upload(client, size=VOICE_NOTE_MAX_BYTES + 1).status_code == 413

    def test_accepts_exactly_5mb(self, client, fake):
        assert _upload(client, size=VOICE_NOTE_MAX_BYTES).status_code == 201

    def test_rejects_over_two_minutes(self, client, fake):
        assert _upload(client, duration='125000').status_code == 400

    def test_two_minute_note_with_flush_grace_is_clamped(self, client, fake):
        resp = _upload(client, duration='121000')
        assert resp.status_code == 201
        assert resp.get_json()['duration_ms'] == 120000

    def test_requires_node_path_and_duration(self, client, fake):
        assert _upload(client, node_path='').status_code == 400
        assert _upload(client, duration='').status_code == 400
        assert _upload(client, duration='abc').status_code == 400

    def test_empty_file_rejected(self, client, fake):
        assert _upload(client, size=0).status_code == 400

    def test_deleted_game_404(self, client, fake):
        fake.store[GAMES_TABLE][0]['deleted_at'] = '2026-10-16T00:00:00+00:00'
        assert _upload(client).status_code == 404


# ─── Signed URL ──────────────────────────────────────────────────────────────

class TestVoiceNoteUrl:
    def test_owner_gets_signed_url(self, client, fake):
        resp = client.get(f'/api/games/{GAME_ID}/voice-notes/note-1/url', headers=AUTH)
        assert resp.status_code == 200
        body = resp.get_json()
        assert body['url'].startswith('https://signed.example/user_a/game-1/note1.webm')
        assert body['expires_in'] == 300

    def test_viewer_with_token_gets_signed_url(self, client, fake, as_user):
        with as_user(USER_B):
            resp = client.get(f'/api/games/{GAME_ID}/voice-notes/note-1/url?share_token={TOKEN}', headers=AUTH)
        assert resp.status_code == 200

    def test_stranger_gets_404(self, client, fake, as_user):
        with as_user(USER_B):
            resp = client.get(f'/api/games/{GAME_ID}/voice-notes/note-1/url', headers=AUTH)
        assert resp.status_code == 404

    def test_note_of_other_game_404(self, client, fake):
        fake.store[VOICE_NOTES_TABLE].append(_note(9, 'e4', game_id='game-other'))
        resp = client.get(f'/api/games/{GAME_ID}/voice-notes/note-9/url', headers=AUTH)
        assert resp.status_code == 404


# ─── Delete ──────────────────────────────────────────────────────────────────

class TestDeleteVoiceNote:
    def test_owner_deletes_row_and_object(self, client, fake):
        resp = client.delete(f'/api/games/{GAME_ID}/voice-notes/note-1', headers=AUTH)
        assert resp.status_code == 200
        assert 'note-1' not in {r['id'] for r in fake.store[VOICE_NOTES_TABLE]}
        assert fake.storage_state['removed'] == [f'{USER_A}/{GAME_ID}/note1.webm']

    def test_viewer_with_token_cannot_delete(self, client, fake, as_user):
        with as_user(USER_B):
            resp = client.delete(f'/api/games/{GAME_ID}/voice-notes/note-1?share_token={TOKEN}', headers=AUTH)
        assert resp.status_code == 404
        assert len(fake.store[VOICE_NOTES_TABLE]) == 4

    def test_stranger_cannot_delete(self, client, fake, as_user):
        with as_user(USER_B):
            assert client.delete(f'/api/games/{GAME_ID}/voice-notes/note-1', headers=AUTH).status_code == 404

    def test_unknown_note_404(self, client, fake):
        assert client.delete(f'/api/games/{GAME_ID}/voice-notes/nope', headers=AUTH).status_code == 404


class TestDeleteMoveVoiceNotes:
    def test_removes_notes_on_the_move_and_after_it(self, client, fake):
        resp = client.delete(f'/api/games/{GAME_ID}/voice-notes?node_path=e4%20e5', headers=AUTH)
        assert resp.status_code == 200
        assert resp.get_json()['deleted'] == 2
        assert {r['node_path'] for r in fake.store[VOICE_NOTES_TABLE]} == {'e4', 'd4'}
        assert sorted(fake.storage_state['removed']) == [
            f'{USER_A}/{GAME_ID}/note2.webm', f'{USER_A}/{GAME_ID}/note3.webm',
        ]

    def test_prefix_match_is_by_whole_move(self, client, fake):
        fake.store[VOICE_NOTES_TABLE].append(_note(5, 'e4 e5x'))
        client.delete(f'/api/games/{GAME_ID}/voice-notes?node_path=e4%20e5', headers=AUTH)
        assert 'e4 e5x' in {r['node_path'] for r in fake.store[VOICE_NOTES_TABLE]}

    def test_viewer_cannot_prune(self, client, fake, as_user):
        with as_user(USER_B):
            resp = client.delete(f'/api/games/{GAME_ID}/voice-notes?node_path=e4&share_token={TOKEN}', headers=AUTH)
        assert resp.status_code == 404
        assert len(fake.store[VOICE_NOTES_TABLE]) == 4

    def test_requires_node_path(self, client, fake):
        assert client.delete(f'/api/games/{GAME_ID}/voice-notes', headers=AUTH).status_code == 400


# ─── Cleanup with the game / database ────────────────────────────────────────

class TestGameDeleteCleanup:
    def test_deleting_game_removes_its_notes_and_objects(self, client, fake):
        fake.store[VOICE_NOTES_TABLE].append(_note(7, 'e4', game_id='game-keep'))
        resp = client.delete(f'/api/games/{GAME_ID}', headers=AUTH)
        assert resp.status_code == 200
        assert {r['game_id'] for r in fake.store[VOICE_NOTES_TABLE]} == {'game-keep'}
        assert len(fake.storage_state['removed']) == 4
        assert f'{USER_A}/game-keep/note7.webm' not in fake.storage_state['removed']


class TestDatabaseHardDeleteCleanup:
    def test_expired_database_removes_voice_note_objects(self, fake):
        from commands.cleanup_deleted_databases import cleanup_deleted_databases

        now = datetime(2026, 10, 16, tzinfo=timezone.utc)
        fake.store[DATABASES_TABLE][0]['deleted_at'] = (now - timedelta(days=40)).isoformat()
        with patch('commands.cleanup_deleted_databases.supabase', fake):
            summary = cleanup_deleted_databases(now=now)

        assert summary['databases'] == 1
        assert len(fake.storage_state['removed']) == 4
        assert fake.store[VOICE_NOTES_TABLE] == []


class _NotNull:
    """`.not_.is_('deleted_at', 'null')` for the fake: keep non-NULL rows."""
    def __init__(self, query):
        self._q = query

    def is_(self, col, val):
        self._q._filters.append(lambda r: r.get(col) is not None)
        return self._q


# ─── Copy to workspace ───────────────────────────────────────────────────────

class TestCopyDuplicatesVoiceNotes:
    def test_copy_duplicates_rows_and_objects_under_copier(self, client, fake, as_user):
        with as_user(USER_B):
            resp = client.post(f'/api/databases/shared/{TOKEN}/copy', headers=AUTH)
        assert resp.status_code == 201
        new_db_id = resp.get_json()['id']

        [copied_game] = [g for g in fake.store[GAMES_TABLE] if g.get('database_id') == new_db_id]
        assert copied_game['id'] != GAME_ID and copied_game['user_id'] == USER_B

        copies = [n for n in fake.store[VOICE_NOTES_TABLE] if n['game_id'] == copied_game['id']]
        assert sorted(n['node_path'] for n in copies) == ['d4', 'e4', 'e4 e5', 'e4 e5 Nf3']
        for n in copies:
            assert n['owner_user_id'] == USER_B
            assert n['storage_path'].startswith(f"{USER_B}/{copied_game['id']}/")
            assert n['storage_path'].endswith('.webm')
            assert n['storage_path'] in fake.storage_state['objects']

        # Originals untouched, so deleting the source later can't break the copy.
        assert len([n for n in fake.store[VOICE_NOTES_TABLE] if n['game_id'] == GAME_ID]) == 4

    def test_copy_survives_a_failed_object_copy(self, client, fake, as_user):
        def boom(self, from_path, to_path):
            raise RuntimeError('storage down')

        with as_user(USER_B), patch.object(FakeBucket, 'copy', boom):
            resp = client.post(f'/api/databases/shared/{TOKEN}/copy', headers=AUTH)
        assert resp.status_code == 201
        assert resp.get_json()['game_count'] == 1
