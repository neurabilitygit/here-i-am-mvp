import hashlib
import json
import subprocess
import sys

import pytest


@pytest.mark.parametrize('unsafe', ['../outside.txt', '/tmp/outside.txt', 'nested/../../outside.txt'])
def test_restore_rejects_escaping_paths_before_writing(tmp_path, unsafe):
    backup = tmp_path / 'backup'
    backup.mkdir()
    target = tmp_path / 'target'
    (backup / 'manifest.json').write_text(json.dumps({'files':[{'path':unsafe, 'bytes':1, 'sha256':'bad'}]}))
    result = subprocess.run([sys.executable, 'scripts/restore_backup.py', str(backup), str(target), '--confirm-empty-target'], capture_output=True)
    assert result.returncode != 0
    assert b'Unsafe' in result.stderr
    assert not target.exists()


def test_restore_rejects_vector_export_without_manifest_hash(tmp_path):
    backup = tmp_path / 'backup'
    (backup / 'appdata').mkdir(parents=True)
    (backup / 'source').write_bytes(b'x')
    (backup / 'appdata/chroma-export.jsonl').write_text('')
    (backup / 'manifest.json').write_text(json.dumps({'files':[{'path':'source', 'bytes':1, 'sha256':hashlib.sha256(b'x').hexdigest()}]}))
    target = tmp_path / 'target'
    result = subprocess.run([sys.executable, 'scripts/restore_backup.py', str(backup), str(target), '--confirm-empty-target'], capture_output=True)
    assert result.returncode != 0
    assert b'missing from the verified file manifest' in result.stderr
    assert not target.exists()
