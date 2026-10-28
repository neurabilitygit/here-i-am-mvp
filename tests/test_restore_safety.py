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


def test_restore_portable_copy_does_not_set_macos_flags(tmp_path, monkeypatch):
    from scripts import restore_backup
    source=tmp_path/'source'; destination=tmp_path/'destination'
    source.write_bytes(b'portable recording contents')
    source.chmod(0o600)
    def unsupported(*args,**kwargs):
        raise OSError(22,'ExFAT does not support macOS file flags')
    monkeypatch.setattr(restore_backup.shutil,'copystat',unsupported)
    restore_backup.restore_file(source,destination,expected_bytes=source.stat().st_size,
                                expected_sha256=restore_backup.digest(source))
    assert destination.read_bytes()==source.read_bytes()
    assert destination.stat().st_mtime_ns==source.stat().st_mtime_ns
    assert destination.stat().st_mode & 0o777==0o600


def test_restore_verifies_written_contents(tmp_path, monkeypatch):
    from scripts import restore_backup
    source=tmp_path/'source'; destination=tmp_path/'destination'
    source.write_bytes(b'original')
    monkeypatch.setattr(restore_backup.shutil,'copyfile',lambda _source,dest:dest.write_bytes(b'corrupt!'))
    with pytest.raises(RuntimeError,match='verification failed'):
        restore_backup.restore_file(source,destination,expected_bytes=source.stat().st_size,
                                    expected_sha256=restore_backup.digest(source))
    assert source.read_bytes()==b'original'


def test_restore_does_not_hide_permission_errors(tmp_path,monkeypatch):
    from scripts import restore_backup
    source=tmp_path/'source'; source.write_bytes(b'preserve')
    def denied(*args,**kwargs):
        raise PermissionError('synthetic access denied')
    monkeypatch.setattr(restore_backup.shutil,'copymode',denied)
    with pytest.raises(PermissionError):
        restore_backup.restore_file(source,tmp_path/'destination',expected_bytes=8,
                                    expected_sha256=restore_backup.digest(source))
