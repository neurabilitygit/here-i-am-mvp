from __future__ import annotations

import json
import errno
import hashlib
import os
import shutil
import tempfile
import time
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fcntl

from slugify import slugify

from config import settings


class LibraryBusyError(RuntimeError):
    pass


def retry_filesystem(operation, *, missing_ok_to_retry: bool = False):
    """Retry only idempotent operations and explicitly transient OS failures.

    Permission, full-disk, invalid JSON, and persistent failures remain errors.
    Never wrap an append or streamed upload in this helper.
    """
    transient = {errno.EAGAIN, errno.EBUSY, errno.EINTR, errno.EIO, errno.ETIMEDOUT, errno.ESTALE}
    for attempt, delay in enumerate((0, .02, .05, .1, .25, .5)):
        if delay:
            time.sleep(delay)
        try:
            return operation()
        except OSError as exc:
            retryable = exc.errno in transient or (missing_ok_to_retry and isinstance(exc, FileNotFoundError))
            if not retryable or attempt == 5:
                raise


def verify_saved_file(path: Path, expected_bytes: int, expected_sha256: str) -> None:
    def verify():
        digest = hashlib.sha256()
        size = 0
        with path.open('rb') as handle:
            while chunk := handle.read(1024 * 1024):
                size += len(chunk)
                digest.update(chunk)
        if not size or size != expected_bytes or digest.hexdigest() != expected_sha256:
            raise ValueError('Saved recording did not match the received audio')
    retry_filesystem(verify, missing_ok_to_retry=True)


@contextmanager
def library_write_lock(*, blocking: bool = True):
    """Serialize library mutations and point-in-time snapshots."""
    Path(settings.locks_dir).mkdir(parents=True, exist_ok=True)
    lock_path = Path(settings.locks_dir) / 'library-write.lock'
    with lock_path.open('a+', encoding='utf-8') as handle:
        operation = fcntl.LOCK_EX | (0 if blocking else fcntl.LOCK_NB)
        try:
            fcntl.flock(handle.fileno(), operation)
        except BlockingIOError as exc:
            raise LibraryBusyError('The memory library is busy with another protected operation') from exc
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


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
        Path(settings.speakers_dir),
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
            'state_version': 4,
            'session_id': session_id,
            'recorded': True,
            'transcribed': False,
            'analyzed': False,
            'embedded': False,
            'transcription_status': 'pending',
            'analysis_status': 'pending',
            'embedding_status': 'pending',
            'active_content_version': None,
            'recording_mode': 'solo',
            'speaker_processing_status': 'not_required',
            'speaker_review_status': 'not_required',
            'updated_at': datetime.now(timezone.utc).isoformat(),
        },
    )
    return session_id, session_path


def save_json(path: Path, data: dict[str, Any]) -> None:
    atomic_write_text(path, json.dumps(data, indent=2, ensure_ascii=False))


def atomic_write_text(path: Path, text: str) -> None:
    retry_filesystem(lambda: _atomic_write_text_once(path, text))


def _atomic_write_text_once(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as handle:
            handle.write(text)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        # Persist the directory entry as well as the file contents. This is
        # important for the external-volume deployment: after a power loss an
        # fsynced temporary file is not sufficient unless the rename itself is
        # durably recorded by the parent directory.
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temp_path.unlink(missing_ok=True)


def atomic_write_bytes(path: Path, payload: bytes) -> None:
    retry_filesystem(lambda: _atomic_write_bytes_once(path, payload))


def _atomic_write_bytes_once(path: Path, payload: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, temp_name = tempfile.mkstemp(prefix=f'.{path.name}.', suffix='.tmp', dir=path.parent)
    temp_path = Path(temp_name)
    try:
        with os.fdopen(fd, 'wb') as handle:
            handle.write(payload)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, path)
        directory_fd = os.open(path.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    finally:
        temp_path.unlink(missing_ok=True)


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def update_processing_state(session_path: Path, **updates: Any) -> None:
    state_path = session_path / 'processing_state.json'
    # External volumes can briefly report the freshly replaced state file as
    # missing even after the durable create has completed. Avoid the
    # exists-then-open race and give the volume a bounded chance to make the
    # directory entry visible before failing closed.
    # Do not replace unreadable/missing existing state with an empty document:
    # that can silently erase seal, consent, and active vector-version fields.
    state = retry_filesystem(lambda: load_json(state_path), missing_ok_to_retry=True)
    state.update(updates)
    state['state_version'] = max(int(state.get('state_version', 2)), 4)
    state['updated_at'] = datetime.now(timezone.utc).isoformat()
    save_json(state_path, state)


def seal_until(session_path: Path, unlock_at: datetime) -> None:
    if not session_path.exists():
        raise FileNotFoundError('Session does not exist')
    with session_lock(session_path.name):
        update_processing_state(session_path, unlock_at=unlock_at.isoformat())


def session_paths(session_path: Path) -> dict[str, Path]:
    return {
        'audio': session_path / 'recording.flac',
        'source_audio': session_path / 'recording.source',
        'transcript': session_path / 'transcript.md',
        'asr_segments': session_path / 'asr.segments.json',
        'diarization': session_path / 'diarization.json',
        'speaker_assignments': session_path / 'speaker_assignments.json',
        'transcript_turns': session_path / 'transcript.turns.json',
        'memory_units': session_path / 'memory_units.jsonl',
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
    with session_lock(session_id):
        shutil.move(str(source), str(target))
        directory_fd = os.open(target.parent, os.O_RDONLY)
        try:
            os.fsync(directory_fd)
        finally:
            os.close(directory_fd)
    return target
