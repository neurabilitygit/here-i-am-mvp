import json
import errno
import hashlib

import pytest

from services import storage
from services.storage import (
    atomic_write_text,
    create_session_dir,
    ensure_directories,
    revise_transcript,
    safe_session_dir,
    session_paths,
)


def test_session_creation_is_unique_and_versioned():
    ensure_directories()
    first_id, first = create_session_dir('A memory')
    second_id, second = create_session_dir('A memory')
    assert first_id != second_id
    assert first.exists() and second.exists()
    state = json.loads(session_paths(first)['state'].read_text())
    assert state['state_version'] == 4
    assert state['recorded'] is True


def test_safe_session_path_rejects_traversal():
    with pytest.raises(ValueError):
        safe_session_dir('../outside')


def test_processing_state_update_retries_a_transient_external_volume_miss(monkeypatch):
    _, session = create_session_dir('Transient state visibility')
    real_load_json = storage.load_json
    attempts = 0

    def intermittently_missing(path):
        nonlocal attempts
        attempts += 1
        if attempts < 3:
            raise FileNotFoundError(path)
        return real_load_json(path)

    monkeypatch.setattr(storage, 'load_json', intermittently_missing)

    storage.update_processing_state(session, upload_status='receiving')

    state = json.loads(session_paths(session)['state'].read_text())
    assert attempts == 3
    assert state['recorded'] is True
    assert state['upload_status'] == 'receiving'


def test_transcript_revision_preserves_previous_text():
    _, session = create_session_dir('Revision')
    transcript = session_paths(session)['transcript']
    atomic_write_text(transcript, 'original')
    revision = revise_transcript(session, 'corrected', 'test correction')
    assert revision.read_text() == 'original'
    assert transcript.read_text() == 'corrected'
    state = json.loads(session_paths(session)['state'].read_text())
    assert state['analysis_status'] == 'stale'
    assert state['embedded'] is False


def test_atomic_write_retries_transient_replace_without_losing_contents(monkeypatch, tmp_path):
    destination = tmp_path / 'state.json'
    destination.write_text('old')
    replace = storage.os.replace
    calls = []
    def intermittent(source, target):
        calls.append(1)
        if len(calls) < 3:
            raise OSError(errno.EIO, 'temporary device error')
        return replace(source, target)
    monkeypatch.setattr(storage.os, 'replace', intermittent)
    monkeypatch.setattr(storage.time, 'sleep', lambda _: None)
    atomic_write_text(destination, 'new')
    assert destination.read_text() == 'new'
    assert len(calls) == 3
    assert list(tmp_path.glob('*.tmp')) == []


@pytest.mark.parametrize('code,expected_attempts', [(errno.EIO, 6), (errno.ENOSPC, 1), (errno.EACCES, 1)])
def test_filesystem_retry_is_bounded_and_does_not_hide_permanent_errors(monkeypatch, code, expected_attempts):
    calls = []
    def fail():
        calls.append(1)
        raise OSError(code, 'synthetic')
    monkeypatch.setattr(storage.time, 'sleep', lambda _: None)
    with pytest.raises(OSError):
        storage.retry_filesystem(fail)
    assert len(calls) == expected_attempts


def test_missing_state_is_not_silently_recreated(monkeypatch):
    _, session = create_session_dir('Missing state')
    original = session_paths(session)['state'].read_bytes()
    def missing(_):
        raise FileNotFoundError('synthetic')
    monkeypatch.setattr(storage, 'load_json', missing)
    monkeypatch.setattr(storage.time, 'sleep', lambda _: None)
    with pytest.raises(FileNotFoundError):
        storage.update_processing_state(session, embedded=False)
    assert session_paths(session)['state'].read_bytes() == original


def test_saved_audio_verification_rejects_same_size_corruption(tmp_path):
    path = tmp_path / 'recording.source'
    path.write_bytes(b'original')
    digest = hashlib.sha256(b'original').hexdigest()
    storage.verify_saved_file(path, 8, digest)
    path.write_bytes(b'changed!')
    with pytest.raises(ValueError):
        storage.verify_saved_file(path, 8, digest)
