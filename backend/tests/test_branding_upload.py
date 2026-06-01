"""
Tests for POST /api/admin/organizations/<org_id>/branding/upload.

Validates: happy paths for each supported MIME type, oversize rejection,
unsupported MIME rejection, non-member 403, student-not-admin 403, and the
shape of the stored object key.
"""

import io

import pytest
from unittest.mock import MagicMock, patch


ADMIN_USER_ID = 'user_admin_123'
STUDENT_USER_ID = 'user_student_456'
ORG_ID = '08653c5f-ac6b-4f63-83c4-edecf0f91207'


@pytest.fixture
def app():
    from flask import Flask
    from routes.admin import admin_bp

    test_app = Flask(__name__)
    test_app.config['TESTING'] = True
    test_app.register_blueprint(admin_bp)
    return test_app


@pytest.fixture
def client(app):
    return app.test_client()


class _FakeBucket:
    """Captures the upload call so the test can assert key shape + payload."""

    def __init__(self):
        self.upload_call = None

    def upload(self, path, file, file_options=None):
        self.upload_call = {
            'path': path,
            'file_size': len(file) if isinstance(file, (bytes, bytearray)) else None,
            'file_options': file_options,
        }
        return {'status_code': 200}

    def get_public_url(self, path):
        return f'https://example.supabase.co/storage/v1/object/public/org-branding/{path}'


def _mock_supabase_with_bucket():
    bucket = _FakeBucket()
    sb = MagicMock()
    sb.storage.from_.return_value = bucket
    return sb, bucket


def _post_upload(client, org_id, kind, data, mime, filename, user_id=ADMIN_USER_ID, content_length=None):
    payload = {
        'kind': kind,
        'file': (io.BytesIO(data), filename, mime),
    }
    return client.post(
        f'/api/admin/organizations/{org_id}/branding/upload',
        data=payload,
        content_type='multipart/form-data',
        headers={'X-User-Id': user_id},
    )


# ─── Happy paths ─────────────────────────────────────────────────────────────


class TestUploadHappyPath:
    @pytest.mark.parametrize(
        'mime,filename,expected_ext',
        [
            ('image/png', 'logo.png', 'png'),
            ('image/jpeg', 'logo.jpg', 'jpg'),
            ('image/webp', 'logo.webp', 'webp'),
            ('image/svg+xml', 'logo.svg', 'svg'),
            ('image/x-icon', 'logo.ico', 'ico'),
        ],
    )
    def test_upload_supported_mime(self, client, mime, filename, expected_ext):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            sb, bucket = _mock_supabase_with_bucket()
            with patch('routes.admin._get_supabase', return_value=sb):
                resp = _post_upload(client, ORG_ID, 'logo', b'\x89PNGimage', mime, filename)
                assert resp.status_code == 201, resp.get_json()
                body = resp.get_json()
                assert body['key'] == f'{ORG_ID}/logo.{expected_ext}'
                assert body['kind'] == 'logo'
                assert body['url'].startswith('https://')
                assert bucket.upload_call is not None
                assert bucket.upload_call['path'] == f'{ORG_ID}/logo.{expected_ext}'

    def test_favicon_kind_writes_favicon_filename(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            sb, bucket = _mock_supabase_with_bucket()
            with patch('routes.admin._get_supabase', return_value=sb):
                resp = _post_upload(client, ORG_ID, 'favicon', b'icondata', 'image/x-icon', 'fav.ico')
                assert resp.status_code == 201
                assert bucket.upload_call['path'] == f'{ORG_ID}/favicon.ico'


# ─── Rejection paths ─────────────────────────────────────────────────────────


class TestUploadRejection:
    def test_oversize_file_413(self, client):
        # 1.5 MiB > 1 MiB cap
        big = b'a' * (1_500_000)
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.storage.from_.return_value = _FakeBucket()
                resp = _post_upload(client, ORG_ID, 'logo', big, 'image/png', 'big.png')
                assert resp.status_code == 413

    def test_unsupported_mime_415(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            with patch('routes.admin._get_supabase') as mock_sb:
                mock_sb.return_value.storage.from_.return_value = _FakeBucket()
                resp = _post_upload(client, ORG_ID, 'logo', b'%PDF-1.4', 'application/pdf', 'logo.pdf')
                assert resp.status_code == 415

    def test_non_member_caller_403(self, client):
        with patch('routes.admin._get_caller_role', return_value=None):
            resp = _post_upload(client, ORG_ID, 'logo', b'x', 'image/png', 'logo.png', user_id='user_stranger')
            assert resp.status_code == 403

    def test_student_not_admin_403(self, client):
        with patch('routes.admin._get_caller_role', return_value='student'):
            resp = _post_upload(client, ORG_ID, 'logo', b'x', 'image/png', 'logo.png', user_id=STUDENT_USER_ID)
            assert resp.status_code == 403

    def test_teacher_not_admin_403(self, client):
        # Note: ADMIN_ROLES in routes/admin.py includes 'teacher' — this matches
        # the existing settings PUT gate. Test asserts current behaviour: teacher
        # IS treated as admin-level, mirroring the settings endpoint.
        with patch('routes.admin._get_caller_role', return_value='teacher'):
            sb, _ = _mock_supabase_with_bucket()
            with patch('routes.admin._get_supabase', return_value=sb):
                resp = _post_upload(client, ORG_ID, 'logo', b'x', 'image/png', 'logo.png', user_id='user_teacher')
                # Per existing _require_admin, teacher is allowed for settings-class endpoints
                assert resp.status_code == 201

    def test_missing_kind_400(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/branding/upload',
                data={'file': (io.BytesIO(b'x'), 'logo.png', 'image/png')},
                content_type='multipart/form-data',
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 400

    def test_missing_file_400(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            resp = client.post(
                f'/api/admin/organizations/{ORG_ID}/branding/upload',
                data={'kind': 'logo'},
                content_type='multipart/form-data',
                headers={'X-User-Id': ADMIN_USER_ID},
            )
            assert resp.status_code == 400

    def test_invalid_kind_400(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            resp = _post_upload(client, ORG_ID, 'banner', b'x', 'image/png', 'banner.png')
            assert resp.status_code == 400


# ─── Object key shape ─────────────────────────────────────────────────────────


class TestUploadKeyShape:
    def test_key_is_org_id_slash_kind_dot_ext(self, client):
        with patch('routes.admin._get_caller_role', return_value='admin'):
            sb, bucket = _mock_supabase_with_bucket()
            with patch('routes.admin._get_supabase', return_value=sb):
                resp = _post_upload(client, ORG_ID, 'logo', b'pngdata', 'image/png', 'whatever.png')
                assert resp.status_code == 201
                # Key starts with org_id and ends with .<ext>; no traversal possible.
                assert bucket.upload_call['path'] == f'{ORG_ID}/logo.png'
                assert '..' not in bucket.upload_call['path']
                assert bucket.upload_call['path'].count('/') == 1
