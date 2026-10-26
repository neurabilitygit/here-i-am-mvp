import json

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
