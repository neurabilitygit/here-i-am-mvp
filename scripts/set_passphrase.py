#!/usr/bin/env python3
"""Set or rotate the shared login passphrase for Here I Am.

Writes a PBKDF2-HMAC-SHA256 hash (never the plaintext) to a 0600 file under
the same secret directory used for the native-bridge token. The hash format
here must stay in lockstep with app/services/auth.py's verify_passphrase().
"""
from __future__ import annotations

import getpass
import hashlib
import json
import os
import secrets
import sys
from pathlib import Path

PBKDF2_ITERATIONS = 600_000


def default_secret_dir() -> Path:
    configured = os.environ.get('HERE_I_AM_SECRET_DIR')
    if configured:
        return Path(configured)
    return Path.home() / 'Library' / 'Application Support' / 'Here-I-Am' / 'secrets'


def hash_passphrase(passphrase: str) -> dict:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac('sha256', passphrase.encode('utf-8'), salt, PBKDF2_ITERATIONS)
    return {
        'algorithm': 'pbkdf2_sha256',
        'iterations': PBKDF2_ITERATIONS,
        'salt': salt.hex(),
        'hash': digest.hex(),
    }


def main() -> int:
    secret_dir = default_secret_dir()
    secret_dir.mkdir(parents=True, exist_ok=True)
    target = secret_dir / 'auth_passphrase_hash'

    passphrase = getpass.getpass('New Here I Am login passphrase: ')
    if len(passphrase) < 8:
        print('Passphrase must be at least 8 characters.', file=sys.stderr)
        return 1
    confirm = getpass.getpass('Confirm passphrase: ')
    if passphrase != confirm:
        print('Passphrases did not match; nothing was changed.', file=sys.stderr)
        return 1

    previous_umask = os.umask(0o077)
    try:
        target.write_text(json.dumps(hash_passphrase(passphrase), indent=2), encoding='utf-8')
        target.chmod(0o600)
    finally:
        os.umask(previous_umask)

    print(f'Passphrase hash written to {target}')
    print('Restart Here I Am (./scripts/start.sh) to pick up the new passphrase.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
