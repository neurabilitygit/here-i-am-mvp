from __future__ import annotations

import json
import os
import shutil
import tempfile
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fcntl

from slugify import slugify

from config import settings


def ensure_directories() -> None:
    for path in [
        Path(settings.sessions_dir),
        Path(settings.chroma_dir),
        Path(settings.logs_dir),
        Path(settings.tmp_dir),
        Path(settings.jobs_dir),
        Path(settings.locks_dir),
        Path(settings.exports_dir),
        Path(settings.archive_dir),
        Path(settings.voice_dir),
    ]:
        path.mkdir(parents=True, exist_ok=True)


def create_session_dir(title: str | None = None) -> tuple[str, Path]:
    stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S-%f')
    suffix = slugify(title) if title else 'recording'
    unique = uuid.uuid4().hex[:6]
    session_id = f'{stamp}_{suffix}_{unique}' if suffix else f'{stamp}_{unique}'
    session_path = Path(settings.sessions_dir) / session_id
    session_path.mkdir(parents=True, exist_ok=False)
    save_json(
        session_path / 'processing_state.json',
        {
            'state_version': 2,
            'session_id': session_id,
            'recorded': True,
            'transcribed': False,
            'analyzed': False,
            'embedded': False,
            'transcription_status': 'pending',
            'analysis_status': 'pending',
            'embedding_status': 'pending',
            'updated_at': datetime.now(timezone.utc).isoformat(),
        },
    )
    return session_id, session_path


def save_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def update_processing_state(session_path: Path, **updates: Any) -> None:
    state_path = session_path / 'processing_state.json'
    state = load_json(state_path) if state_path.exists() else {}
    state.update(updates)
    state.setdefault('state_version', 2)
    state['updated_at'] = datetime.now(timezone.utc).isoformat()
    save_json(state_path, state)


def session_paths(session_path: Path) -> dict[str, Path]:
    return {
        'audio': session_path / 'recording.flac',
        'transcript': session_path / 'transcript.md',
        'metadata': session_path / 'metadata.json',
        'chunks': session_path / 'chunks.jsonl',
        'state': session_path / 'processing_state.json',
    }


def list_session_dirs() -> list[Path]:
    sessions_root = Path(settings.sessions_dir)
    if not sessions_root.exists():
        return []
    return sorted([p for p in sessions_root.iterdir() if p.is_dir()])


def safe_session_dir(session_id: str) -> Path:
    if Path(session_id).name != session_id or session_id in {'', '.', '..'}:
        raise ValueError('Invalid session id')
    root = Path(settings.sessions_dir).resolve()
    candidate = (root / session_id).resolve()
    if candidate.parent != root:
        raise ValueError('Invalid session id')
    return candidate


@contextmanager
def session_lock(session_id: str):
    Path(settings.locks_dir).mkdir(parents=True, exist_ok=True)
    lock_path = Path(settings.locks_dir) / f'{slugify(session_id)}.lock'
    with lock_path.open('a+', encoding='utf-8') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def revise_transcript(session_path: Path, transcript: str, reason: str) -> Path:
    paths = session_paths(session_path)
    if not paths['transcript'].exists():
        raise FileNotFoundError('Transcript does not exist')
    revisions = session_path / 'transcript.revisions'
    stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
    revision_path = revisions / f'{stamp}.md'
    revision_path.parent.mkdir(parents=True, exist_ok=True)
    atomic_write_text(revision_path, paths['transcript'].read_text(encoding='utf-8'))
    atomic_write_text(paths['transcript'], transcript)
    save_json(
        revisions / f'{stamp}.json',
        {'created_at': datetime.now(timezone.utc).isoformat(), 'reason': reason},
    )
    update_processing_state(
        session_path,
        transcribed=True,
        analyzed=False,
        embedded=False,
        analysis_status='stale',
        embedding_status='stale',
    )
    return revision_path


def archive_session(session_id: str) -> Path:
    source = safe_session_dir(session_id)
    if not source.exists():
        raise FileNotFoundError('Session does not exist')
    target = Path(settings.archive_dir) / source.name
    if target.exists():
        raise FileExistsError('Session is already archived')
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.move(str(source), str(target))
    return target
