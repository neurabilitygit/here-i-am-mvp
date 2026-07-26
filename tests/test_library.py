import json
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from config import settings
from models.schemas import SessionSummary
from services.library import (
    create_structured_backup,
    days_since_last_recording,
    list_sessions,
    on_this_day_sessions,
    reconciliation_report,
    sealed_sessions,
    session_summary,
)
from services.storage import atomic_write_text, create_session_dir, ensure_directories, save_json, session_paths, update_processing_state


def test_library_summary_and_read_only_reconciliation():
    ensure_directories()
    _, session = create_session_dir('Library test')
    paths = session_paths(session)
    atomic_write_text(paths['transcript'], '# Transcript\n\nA synthetic memory.')
    summaries = list_sessions()
    assert any(item.session_id == session.name and item.transcribed for item in summaries)
    before = paths['state'].read_text()
    report = reconciliation_report()
    after = paths['state'].read_text()
    assert report.repair_applied is False
    assert report.issue_count >= 1
    assert before == after


def test_structured_backup_copies_without_changing_source():
    _, session = create_session_dir('Backup test')
    paths = session_paths(session)
    atomic_write_text(paths['transcript'], 'synthetic')
    paths['audio'].write_bytes(b'synthetic-original-audio')
    archived = Path(settings.archive_dir) / 'archived-memory' / 'recording.source'
    archived.parent.mkdir(parents=True, exist_ok=True)
    archived.write_bytes(b'archived-original-audio')
    source = paths['transcript'].read_bytes()
    result = create_structured_backup()
    assert result['files'] >= 1
    assert paths['transcript'].read_bytes() == source
    backup = Path(settings.backup_root) / result['backup_id']
    manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    backed_up = {item['path'] for item in manifest['files']}
    assert str(paths['audio'].relative_to(Path(settings.data_root))) in backed_up
    assert str(archived.relative_to(Path(settings.data_root))) in backed_up
    assert 'appdata/chroma-export.jsonl' in backed_up
    assert manifest['backup_kind'] == 'full-rebuildable'

    empty_restore = Path(tempfile.mkdtemp(prefix='here-i-am-empty-restore-'))
    verified = subprocess.run(
        [sys.executable, 'scripts/restore_backup.py', str(backup), str(empty_restore)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert verified.returncode == 0
    assert 'Verified' in verified.stdout

    restored = subprocess.run(
        [
            sys.executable,
            'scripts/restore_backup.py',
            str(backup),
            str(empty_restore),
            '--confirm-empty-target',
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    assert restored.returncode == 0, restored.stderr
    assert (empty_restore / paths['audio'].relative_to(Path(settings.data_root))).read_bytes() == b'synthetic-original-audio'
    assert (empty_restore / archived.relative_to(Path(settings.data_root))).read_bytes() == b'archived-original-audio'


def test_session_summary_exposes_metadata_derived_fields():
    ensure_directories()
    _, session = create_session_dir('Metadata fields test')
    save_json(session_paths(session)['metadata'], {
        'title': 'Metadata fields test',
        'topics': ['gardening', 'family'],
        'time_period': '1990s',
        'emotional_tone': ['joyful', 'nostalgic'],
        'notable_events': ['first harvest'],
    })
    summary = session_summary(session)
    assert summary.topics == ['gardening', 'family']
    assert summary.time_period == '1990s'
    assert summary.emotional_tone == ['joyful', 'nostalgic']
    assert summary.notable_events == ['first harvest']
    assert summary.recorded_at == session.name[:10]


def _fake_summary(session_id: str, recorded_at: str, sealed: bool = False) -> SessionSummary:
    return SessionSummary(
        session_id=session_id, title=session_id, recorded=True, transcribed=True,
        analyzed=True, embedded=True, recorded_at=recorded_at, sealed=sealed,
    )


def test_on_this_day_sessions_matches_month_day_across_years_excludes_current_year(monkeypatch):
    reference = date(2026, 6, 15)
    fake_sessions = [
        _fake_summary('past-year-match', '2020-06-15'),
        _fake_summary('current-year-same-day', f'{reference.year}-06-15'),
        _fake_summary('unrelated-date', '2021-03-02'),
        _fake_summary('sealed-same-day', '2019-06-15', sealed=True),
    ]
    monkeypatch.setattr('services.library.list_sessions', lambda: fake_sessions)
    matched_ids = {item.session_id for item in on_this_day_sessions(today=reference)}
    assert matched_ids == {'past-year-match'}


def test_days_since_last_recording_uses_most_recent_session(monkeypatch):
    newer = (date.today() - timedelta(days=2)).isoformat()
    older = (date.today() - timedelta(days=10)).isoformat()
    monkeypatch.setattr('services.library.list_sessions', lambda: [_fake_summary('newer', newer), _fake_summary('older', older)])
    assert days_since_last_recording() == 2

    monkeypatch.setattr('services.library.list_sessions', lambda: [])
    assert days_since_last_recording() is None


def test_list_sessions_omits_sealed_sessions_until_unlock_date_passes():
    ensure_directories()
    _, session = create_session_dir('Sealed listing test')
    future = (datetime.now(timezone.utc) + timedelta(days=1)).isoformat()
    update_processing_state(session, unlock_at=future)

    assert not any(item.session_id == session.name for item in list_sessions())
    assert any(item.session_id == session.name and item.unlock_at == future for item in sealed_sessions())

    past = (datetime.now(timezone.utc) - timedelta(days=1)).isoformat()
    update_processing_state(session, unlock_at=past)
    assert any(item.session_id == session.name for item in list_sessions())
    assert not any(item.session_id == session.name for item in sealed_sessions())


def test_session_summary_treats_non_string_unlock_at_as_unsealed():
    ensure_directories()
    _, session = create_session_dir('Non-string unlock test')
    update_processing_state(session, unlock_at=12345)
    summary = session_summary(session)
    assert summary.sealed is False
    assert any(item.session_id == session.name for item in list_sessions())
