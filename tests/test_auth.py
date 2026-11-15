import json
import pytest
from datetime import datetime, timezone
from pathlib import Path

from fastapi.testclient import TestClient

import main
import services.auth as auth
from config import settings

TEST_PASSPHRASE = 'correct horse battery staple'


def _configure_auth(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'auth_disabled', False)
    hash_path = tmp_path / 'auth_passphrase_hash.json'
    hash_path.write_text(json.dumps(auth.hash_passphrase(TEST_PASSPHRASE)), encoding='utf-8')
    monkeypatch.setattr(settings, 'auth_passphrase_hash_file', str(hash_path))
    monkeypatch.setattr(settings, 'auth_tokens_path', str(tmp_path / 'auth_tokens.json'))
    monkeypatch.setattr(settings, 'auth_max_failed_attempts', 3)
    monkeypatch.setattr(settings, 'auth_lockout_seconds', 900)
    auth.register_success()  # clear lockout state left over from another test
    return TestClient(main.app)


def test_auth_can_be_explicitly_disabled_for_isolated_tests():
    client = TestClient(main.app)
    assert client.get('/api/sessions').status_code == 200
    status = client.get('/api/auth/status')
    assert status.status_code == 200
    assert status.json() == {'authenticated': False, 'required': False}


def test_protected_route_rejects_missing_token(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    assert client.get('/api/sessions').status_code == 401


def test_auth_is_required_without_provisioning(monkeypatch):
    monkeypatch.setattr(settings, 'auth_disabled', False)
    monkeypatch.setattr(settings, 'auth_passphrase_hash_file', '')
    client = TestClient(main.app)
    assert client.get('/api/sessions').status_code == 503
    assert client.get('/api/auth/status').json()['required'] is True
    assert client.post('/api/auth/login', json={'passphrase': TEST_PASSPHRASE}).status_code == 401


@pytest.mark.parametrize('failure', ['missing', 'unreadable', 'json', 'schema', 'encoding'])
@pytest.mark.parametrize('authenticated', [False, True])
def test_credential_failure_denies_access_and_recovers(tmp_path, monkeypatch, failure, authenticated):
    client = _configure_auth(tmp_path, monkeypatch)
    if authenticated:
        assert client.post('/api/auth/login', json={'passphrase': TEST_PASSPHRASE}).status_code == 200
    hash_path = Path(settings.auth_passphrase_hash_file)
    original = hash_path.read_bytes()
    read_text = Path.read_text
    with monkeypatch.context() as patch:
        if failure == 'missing':
            hash_path.unlink()
        elif failure == 'unreadable':
            def deny(path, *args, **kwargs):
                if path == hash_path:
                    raise PermissionError('isolated simulated permission failure')
                return read_text(path, *args, **kwargs)
            patch.setattr(Path, 'read_text', deny)
        else:
            hash_path.write_bytes({'json': b'{', 'schema': b'[]', 'encoding': b'\xff'}[failure])
        assert client.get('/api/sessions').status_code == 503
        assert client.post('/api/chat', json={}).status_code == 503
        assert client.get('/api/auth/status').json() == {'authenticated': False, 'required': True}
        assert client.post('/api/auth/login', json={'passphrase': TEST_PASSPHRASE}).status_code == 401
        assert client.get('/').status_code == 200
    hash_path.write_bytes(original)
    assert client.get('/api/sessions').status_code == (200 if authenticated else 401)


def test_auth_default_is_enabled():
    from config import Settings
    assert Settings.model_fields['auth_disabled'].default is False


def test_protected_route_rejects_invalid_token(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    client.cookies.set(auth.SESSION_COOKIE_NAME, 'not-a-real-token')
    assert client.get('/api/sessions').status_code == 401


def test_public_allowlist_reachable_without_cookie(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    assert client.get('/').status_code == 200
    assert client.get('/static/styles.css').status_code == 200
    assert client.get('/api/health').status_code == 200
    assert client.get('/api/ready').status_code in (200, 503)
    status = client.get('/api/auth/status')
    assert status.status_code == 200
    assert status.json() == {'authenticated': False, 'required': True}


def test_login_failure_wrong_passphrase(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    response = client.post('/api/auth/login', json={'passphrase': 'wrong passphrase'})
    assert response.status_code == 401
    assert auth.SESSION_COOKIE_NAME not in response.cookies


def test_login_success_sets_cookie_and_allows_access(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    response = client.post('/api/auth/login', json={'passphrase': TEST_PASSPHRASE})
    assert response.status_code == 200
    assert response.json()['authenticated'] is True
    assert client.cookies.get(auth.SESSION_COOKIE_NAME)
    assert client.get('/api/sessions').status_code == 200
    assert client.get('/api/auth/status').json() == {'authenticated': True, 'required': True}


def test_login_lockout_after_repeated_failures(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    for _ in range(3):
        assert client.post('/api/auth/login', json={'passphrase': 'wrong'}).status_code == 401
    locked = client.post('/api/auth/login', json={'passphrase': TEST_PASSPHRASE})
    assert locked.status_code == 429


def test_logout_invalidates_token(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    client.post('/api/auth/login', json={'passphrase': TEST_PASSPHRASE})
    assert client.get('/api/sessions').status_code == 200
    assert client.post('/api/auth/logout').status_code == 200
    assert client.get('/api/sessions').status_code == 401


def test_malformed_expires_at_is_treated_as_expired_not_a_crash():
    moment = datetime.now(timezone.utc)
    assert auth._not_expired({'expires_at': 12345}, moment) is False
    assert auth._not_expired({'expires_at': None}, moment) is False
    assert auth._not_expired({}, moment) is False
    assert auth._not_expired({'expires_at': 'not-a-real-timestamp'}, moment) is False


def test_validate_token_does_not_crash_on_a_malformed_stored_token(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    raw_token = 'whatever-token'
    tokens_path = Path(settings.auth_tokens_path)
    tokens_path.write_text(
        json.dumps({'tokens': [{'token_hash': auth._hash_token(raw_token), 'expires_at': 999999}]}),
        encoding='utf-8',
    )
    client.cookies.set(auth.SESSION_COOKIE_NAME, raw_token)
    assert client.get('/api/sessions').status_code == 401
