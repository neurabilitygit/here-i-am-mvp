from __future__ import annotations

import hashlib
import hmac
import json
import logging
import secrets
import threading
import time
from datetime import datetime, timedelta, timezone
from pathlib import Path

from config import settings
from services.storage import atomic_write_text

logger = logging.getLogger('here_i_am.auth')

SESSION_COOKIE_NAME = 'here_i_am_session'
PBKDF2_ITERATIONS_DEFAULT = 600_000

# A single-user app reached only through a small, already-loopback-facing
# surface: the lockout counter intentionally has one global bucket rather
# than tracking it per client IP, since the real caller IP is not reliably
# visible past Docker's port publishing / Tailscale's local proxying anyway.
_LOCKOUT_KEY = 'global'

_tokens_lock = threading.RLock()
_failed_lock = threading.RLock()
_failed_attempts: list[float] = []

_PUBLIC_EXACT = {
    ('GET', '/'),
    ('GET', '/api/health'),
    # scripts/start.sh polls this during every deploy/restart with no
    # session cookie; gating it would make the launcher's own readiness
    # wait time out and fail every deploy.
    ('GET', '/api/ready'),
    ('POST', '/api/auth/login'),
    ('GET', '/api/auth/status'),
    ('POST', '/api/auth/logout'),
}


def is_path_exempt(method: str, path: str) -> bool:
    if (method, path) in _PUBLIC_EXACT:
        return True
    return method == 'GET' and path.startswith('/static/')


def requires_auth(method: str, path: str) -> bool:
    # The gate only activates once an operator has provisioned a passphrase
    # (scripts/set_passphrase.py). scripts/start.sh refuses to launch the
    # real deployment without one, so this stays fail-closed in production;
    # locally/in CI, where no passphrase is configured, the app behaves as
    # it did before auth existed rather than becoming permanently unusable.
    if not passphrase_configured():
        return False
    return not is_path_exempt(method, path)


def _hash_passphrase(passphrase: str, salt: bytes, iterations: int) -> bytes:
    return hashlib.pbkdf2_hmac('sha256', passphrase.encode('utf-8'), salt, iterations)


def hash_passphrase(passphrase: str, iterations: int = PBKDF2_ITERATIONS_DEFAULT) -> dict:
    salt = secrets.token_bytes(16)
    digest = _hash_passphrase(passphrase, salt, iterations)
    return {
        'algorithm': 'pbkdf2_sha256',
        'iterations': iterations,
        'salt': salt.hex(),
        'hash': digest.hex(),
    }


def _load_passphrase_record() -> dict | None:
    path = settings.auth_passphrase_hash_file
    if not path:
        return None
    try:
        return json.loads(Path(path).read_text(encoding='utf-8'))
    except (OSError, json.JSONDecodeError):
        logger.error('configured auth passphrase hash file is unavailable or invalid')
        return None


def passphrase_configured() -> bool:
    return _load_passphrase_record() is not None


def verify_passphrase(passphrase: str) -> bool:
    record = _load_passphrase_record()
    if not record:
        return False
    try:
        salt = bytes.fromhex(record['salt'])
        iterations = int(record['iterations'])
        expected = bytes.fromhex(record['hash'])
    except (KeyError, ValueError):
        logger.error('auth passphrase hash file is malformed')
        return False
    candidate = _hash_passphrase(passphrase, salt, iterations)
    return hmac.compare_digest(candidate, expected)


def _hash_token(raw_token: str) -> str:
    return hashlib.sha256(raw_token.encode('utf-8')).hexdigest()


def _load_tokens() -> list[dict]:
    path = Path(settings.auth_tokens_path)
    if not path.exists():
        return []
    try:
        return json.loads(path.read_text(encoding='utf-8')).get('tokens', [])
    except (OSError, json.JSONDecodeError):
        logger.error('auth tokens file is invalid; treating as empty')
        return []


def _save_tokens(tokens: list[dict]) -> None:
    atomic_write_text(Path(settings.auth_tokens_path), json.dumps({'tokens': tokens}, indent=2))


def _not_expired(entry: dict, now: datetime) -> bool:
    try:
        return datetime.fromisoformat(entry['expires_at']) > now
    except (KeyError, TypeError, ValueError):
        return False


def issue_token(label: str = '') -> str:
    raw_token = secrets.token_urlsafe(32)
    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=settings.auth_token_ttl_seconds)
    with _tokens_lock:
        tokens = [entry for entry in _load_tokens() if _not_expired(entry, now)]
        tokens.append({
            'token_hash': _hash_token(raw_token),
            'created_at': now.isoformat(),
            'expires_at': expires_at.isoformat(),
            'label': label,
        })
        _save_tokens(tokens)
    return raw_token


def validate_token(raw_token: str) -> bool:
    if not raw_token:
        return False
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    with _tokens_lock:
        tokens = _load_tokens()
    for entry in tokens:
        if entry.get('token_hash') == token_hash:
            return _not_expired(entry, now)
    return False


def revoke_token(raw_token: str) -> None:
    if not raw_token:
        return
    token_hash = _hash_token(raw_token)
    now = datetime.now(timezone.utc)
    with _tokens_lock:
        tokens = [
            entry for entry in _load_tokens()
            if entry.get('token_hash') != token_hash and _not_expired(entry, now)
        ]
        _save_tokens(tokens)


def register_failure() -> None:
    now = time.monotonic()
    with _failed_lock:
        recent = [t for t in _failed_attempts if now - t < settings.auth_lockout_seconds]
        recent.append(now)
        _failed_attempts[:] = recent


def register_success() -> None:
    with _failed_lock:
        _failed_attempts.clear()


def is_locked_out() -> bool:
    now = time.monotonic()
    with _failed_lock:
        recent = [t for t in _failed_attempts if now - t < settings.auth_lockout_seconds]
        _failed_attempts[:] = recent
        return len(recent) >= settings.auth_max_failed_attempts
