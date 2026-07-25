import json

from fastapi.testclient import TestClient

import main
import services.auth as auth
from config import settings

TEST_PASSPHRASE = 'correct horse battery staple'


def _configure_auth(tmp_path, monkeypatch):
    hash_path = tmp_path / 'auth_passphrase_hash.json'
    hash_path.write_text(json.dumps(auth.hash_passphrase(TEST_PASSPHRASE)), encoding='utf-8')
    monkeypatch.setattr(settings, 'auth_passphrase_hash_file', str(hash_path))
    monkeypatch.setattr(settings, 'auth_tokens_path', str(tmp_path / 'auth_tokens.json'))
    monkeypatch.setattr(settings, 'auth_max_failed_attempts', 3)
    monkeypatch.setattr(settings, 'auth_lockout_seconds', 900)
    # httpx's cookie jar (unlike real browsers) withholds Secure cookies on
    # the plain-http TestClient transport; disable Secure only for this check.
    monkeypatch.setattr(settings, 'auth_cookie_secure', False)
    auth.register_success()  # clear lockout state left over from another test
    return TestClient(main.app)


def test_auth_is_inactive_until_a_passphrase_is_configured():
    client = TestClient(main.app)
    assert client.get('/api/sessions').status_code == 200
    status = client.get('/api/auth/status')
    assert status.status_code == 200
    assert status.json() == {'authenticated': False, 'required': False}


def test_protected_route_rejects_missing_token(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    assert client.get('/api/sessions').status_code == 401


def test_protected_route_rejects_invalid_token(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    client.cookies.set(auth.SESSION_COOKIE_NAME, 'not-a-real-token')
    assert client.get('/api/sessions').status_code == 401


def test_public_allowlist_reachable_without_cookie(tmp_path, monkeypatch):
    client = _configure_auth(tmp_path, monkeypatch)
    assert client.get('/').status_code == 200
    assert client.get('/static/styles.css').status_code == 200
    assert client.get('/api/health').status_code == 200
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
