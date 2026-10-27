import importlib.util
from pathlib import Path
import sys

import pytest


def module():
    scripts=Path(__file__).resolve().parents[1]/'scripts'
    sys.path.insert(0,str(scripts))
    try:
        spec=importlib.util.spec_from_file_location('native_backup_rehearsal',scripts/'rehearse_native_backup.py')
        loaded=importlib.util.module_from_spec(spec)
        spec.loader.exec_module(loaded)
        return loaded
    finally:
        sys.path.remove(str(scripts))


@pytest.mark.parametrize('destination',['source/nested','state/nested','/Volumes/Personal/here-i-am/restore','/data/restore'])
def test_rehearsal_rejects_protected_destination(tmp_path,destination):
    rehearsal=module()
    with pytest.raises(ValueError,match='protected'):
        rehearsal.new_destination(tmp_path/destination,tmp_path/'source',tmp_path/'state')


def test_rehearsal_never_reuses_existing_destination(tmp_path):
    rehearsal=module()
    target=tmp_path/'target'; target.mkdir()
    (target/'keep').write_text('preserve')
    with pytest.raises(ValueError,match='new'):
        rehearsal.new_destination(target,tmp_path/'source',tmp_path/'state')
    assert (target/'keep').read_text()=='preserve'


def test_rehearsal_accepts_separate_new_destination(tmp_path):
    rehearsal=module()
    target=tmp_path/'new-copy'
    assert rehearsal.new_destination(target,tmp_path/'source',tmp_path/'state')==target.resolve()
    assert not target.exists()


def test_rehearsal_count_ignores_exfat_sidecars(tmp_path):
    rehearsal=module()
    sessions=tmp_path/'library/sessions'; sessions.mkdir(parents=True)
    (sessions/'real-recording').mkdir()
    (sessions/'._real-recording').write_bytes(b'filesystem metadata')
    (sessions/'not-a-session.txt').write_text('not a folder')
    assert rehearsal.session_count(tmp_path)==1
