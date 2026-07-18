import json

from config import settings
from services.library import create_structured_backup, list_sessions, reconciliation_report
from services.storage import atomic_write_text, create_session_dir, ensure_directories, session_paths


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
    source = paths['transcript'].read_bytes()
    result = create_structured_backup()
    assert result['files'] >= 1
    assert paths['transcript'].read_bytes() == source
