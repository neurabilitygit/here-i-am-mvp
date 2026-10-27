#!/usr/bin/env python3
"""Opt-in local native pilot, NOT a production launcher or migration tool.

Does not start Docker, Tailscale, Ollama, or voice bridges. Foreground only.
Requires a marked isolated data copy and an independent private state directory.
"""
from __future__ import annotations

import argparse
import getpass
import hashlib
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import re
import secrets
import shutil
import socket
import stat
import sys

REPO = Path(__file__).resolve().parents[1]
LOCK = REPO / 'requirements-native-macos-arm64-py311.lock'
PRODUCTION = Path('/Volumes/Personal/here-i-am')
MARKER = '.here-i-am-native-pilot.json'


def inside(path: Path, parent: Path) -> bool:
    return path == parent or parent in path.parents


def validate_paths(root: Path, state: Path) -> tuple[Path, Path]:
    root, state = root.resolve(), state.resolve()
    for path in (root, state):
        if inside(path, PRODUCTION.resolve()) or inside(PRODUCTION.resolve(), path) or inside(path, Path('/data')):
            raise ValueError('Refusing production data paths or their ancestors')
    if inside(state, root) or inside(root, state):
        raise ValueError('Pilot state and data directories must be separate')
    if not (root / 'library/sessions').is_dir() or not (root / 'appdata/chroma/chroma.sqlite3').is_file():
        raise ValueError('Use an existing restored pilot library, not an empty or production directory')
    # Symlinked files could escape the copied library during reads or writes.
    for base in (root, state):
        if base.exists() and any(p.is_symlink() for p in base.rglob('*')):
            raise ValueError('Pilot directories must not contain symlinks')
    if (state / '.env').exists():
        raise ValueError('Pilot state must not contain an environment file')
    return root, state


def write_private_new(path: Path, data: dict) -> None:
    with path.open('x', encoding='utf-8') as f:
        os.chmod(path, 0o600)
        json.dump(data, f, indent=2)
        f.flush()
        os.fsync(f.fileno())


def initialize(root: Path, state: Path, passphrase: str) -> None:
    root, state = validate_paths(root, state)
    if len(passphrase) < 12:
        raise ValueError('Use a separate pilot passphrase of at least 12 characters')
    if (root / MARKER).exists() or state.exists():
        raise ValueError('Already initialized or state directory exists; nothing overwritten')
    state.mkdir(parents=True, mode=0o700)
    os.chmod(state, 0o700)
    salt = secrets.token_bytes(16)
    record = {'algorithm':'pbkdf2_sha256', 'iterations':600000, 'salt':salt.hex(),
              'hash':hashlib.pbkdf2_hmac('sha256',passphrase.encode(),salt,600000).hex()}
    write_private_new(state / 'passphrase.json', record)
    write_private_new(root / MARKER, {'version':1,'data_root':str(root),'state_dir':str(state),'purpose':'isolated-native-pilot'})


def auth_record_valid(path: Path) -> bool:
    try:
        d=json.loads(path.read_text())
        return (not path.is_symlink() and stat.S_IMODE(path.stat().st_mode) == 0o600
                and d['algorithm']=='pbkdf2_sha256' and d['iterations']==600000
                and len(bytes.fromhex(d['salt']))==16 and len(bytes.fromhex(d['hash']))==32)
    except (OSError, ValueError, KeyError, TypeError):
        return False


def check_initialized(root: Path, state: Path) -> tuple[Path, Path]:
    root, state = validate_paths(root, state)
    marker=json.loads((root / MARKER).read_text())
    if marker != {'version':1,'data_root':str(root),'state_dir':str(state),'purpose':'isolated-native-pilot'}:
        raise ValueError('Pilot marker does not match these directories')
    if stat.S_IMODE(state.stat().st_mode) != 0o700 or not auth_record_valid(state/'passphrase.json'):
        raise ValueError('Pilot authentication is missing, invalid, or not private')
    return root, state


def check_runtime() -> None:
    if platform.system() != 'Darwin' or platform.machine() != 'arm64' or sys.version_info[:3] != (3,11,14):
        raise ValueError('Pilot requires the validated macOS arm64 Python 3.11.14 runtime')
    for line in LOCK.read_text().splitlines():
        if not line or line.startswith('#'):
            continue
        name, expected = line.split('==')
        if importlib.metadata.version(name) != expected:
            raise ValueError(f'Native dependency mismatch: {name}')
    for executable in ('ffmpeg','ffprobe'):
        if not shutil.which(executable, path='/opt/homebrew/bin:/usr/bin:/bin'):
            raise ValueError(f'Missing native audio utility: {executable}')


def settings_for(root: Path, state: Path, port: int) -> dict:
    paths = {'sessions_dir':'library/sessions','archive_dir':'library/archive','chroma_dir':'appdata/chroma',
        'logs_dir':'appdata/logs','tmp_dir':'appdata/tmp','jobs_dir':'appdata/jobs','exports_dir':'appdata/exports',
        'backup_root':'appdata/backups','preferences_path':'appdata/preferences.json',
        'fidelity_profile_path':'appdata/speaker_fingerprint.json','feedback_path':'appdata/answer_feedback.jsonl',
        'generation_audit_path':'appdata/generation_audit.jsonl','activity_event_path':'appdata/logs/activity_events.jsonl',
        'voice_dir':'appdata/voice','speakers_dir':'appdata/speakers'}
    values={k:str(root/v) for k,v in paths.items()}
    values.update(data_root=str(root), voice_host_data_root=str(root), locks_dir=str(state/'locks'),
        local_workload_lock_path=str(state/'inference.lock'), auth_tokens_path=str(state/'auth_tokens.json'),
        auth_passphrase_hash_file=str(state/'passphrase.json'), host='127.0.0.1',port=port,
        trusted_hosts='127.0.0.1,localhost', cors_origins=f'http://127.0.0.1:{port}',
        ollama_base_url='http://127.0.0.1:1',ollama_control_url='http://127.0.0.1:1',
        voice_bridge_url='http://127.0.0.1:1',openai_base_url='http://127.0.0.1:1',
        voice_provider='disabled',speaker_diarization_provider='disabled',local_bridge_token='',
        openai_api_key='',openai_api_key_file='',elevenlabs_api_key='',allow_runtime_cloud_key=False,
        app_build_commit='native-pilot',app_build_date='')
    return values


def mutation_allowed(method: str, path: str) -> bool:
    if method in {'GET','HEAD'}:
        return True
    return method == 'POST' and (path in {'/api/auth/login','/api/auth/logout','/api/activity-events','/api/recordings/upload'}
        or bool(re.fullmatch(r'/api/sessions/[A-Za-z0-9_-]+/recording/retry',path)))


def check_port(port: int) -> None:
    with socket.socket() as s:
        # Match uvicorn: TIME_WAIT after our own graceful shutdown is not a
        # competing listener. A genuinely listening server still prevents bind.
        s.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        s.bind(('127.0.0.1',port))


def run(root: Path, state: Path, port: int) -> None:
    if port < 1024 or port > 65535 or port in {8787,8778,8779,11434}:
        raise ValueError('Use a separate unprivileged pilot port (default 8792)')
    root, state = check_initialized(root,state)
    check_runtime()
    check_port(port)  # fail before loading any copied application state
    # Never source .env or inherit provider credentials/data paths from the shell.
    os.environ.clear()
    os.environ.update(PATH='/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                      ANONYMIZED_TELEMETRY='False',OTEL_SDK_DISABLED='true',PYTHONDONTWRITEBYTECODE='1')
    os.chdir(state)
    sys.path.insert(0,str(REPO/'app'))
    import config
    config.settings = config.Settings(_env_file=None, **settings_for(root,state,port))
    from main import app
    from starlette.responses import JSONResponse
    import uvicorn
    @app.middleware('http')
    async def pilot_guard(request, call_next):
        # Existing app supports unconfigured auth for CI. Pilot must fail closed
        # even if its hash disappears after startup.
        if not auth_record_valid(state/'passphrase.json'):
            return JSONResponse({'detail':'Pilot authentication unavailable'},status_code=503)
        if not mutation_allowed(request.method,request.url.path):
            return JSONResponse({'detail':'This operation is disabled in the isolated storage pilot'},status_code=403)
        return await call_next(request)
    print(f'Isolated native pilot: http://127.0.0.1:{port} (Ctrl-C to stop)',flush=True)
    uvicorn.run(app,host='127.0.0.1',port=port,access_log=False,limit_concurrency=32)


def main() -> int:
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['init','check','run'])
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--port',type=int,default=8792)
    p.add_argument('--confirm-isolated-copy',action='store_true')
    args=p.parse_args()
    try:
        if args.command=='init':
            if not args.confirm_isolated_copy:
                raise ValueError('Explicit --confirm-isolated-copy is required')
            password=getpass.getpass('New separate pilot passphrase: ')
            if password != getpass.getpass('Confirm pilot passphrase: '):
                raise ValueError('Passphrases did not match')
            initialize(args.data_root,args.state_dir,password)
        elif args.command=='check':
            check_initialized(args.data_root,args.state_dir)
            check_runtime()
            print('Native pilot paths, authentication, and pinned runtime verified.')
        else:
            run(args.data_root,args.state_dir,args.port)
        return 0
    except (ValueError,OSError,importlib.metadata.PackageNotFoundError) as exc:
        print(f'Pilot refused to start: {exc}',file=sys.stderr)
        return 1


if __name__=='__main__':
    raise SystemExit(main())
