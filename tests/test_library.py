import json
import subprocess
import sys
import tempfile
from pathlib import Path

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
    paths['audio'].write_bytes(b'synthetic-original-audio')
    source = paths['transcript'].read_bytes()
    result = create_structured_backup()
    assert result['files'] >= 1
    assert paths['transcript'].read_bytes() == source
    backup = Path(settings.backup_root) / result['backup_id']
    manifest = json.loads((backup / 'manifest.json').read_text(encoding='utf-8'))
    backed_up = {item['path'] for item in manifest['files']}
    assert str(paths['audio'].relative_to(Path(settings.data_root))) in backed_up
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
