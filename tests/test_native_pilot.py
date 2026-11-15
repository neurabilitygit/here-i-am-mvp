import json
from pathlib import Path
import socket

import pytest

from scripts import native_pilot as pilot


def data_copy(tmp_path):
    root=tmp_path/'copy'
    (root/'library/sessions').mkdir(parents=True)
    (root/'appdata/chroma').mkdir(parents=True)
    (root/'appdata/chroma/chroma.sqlite3').write_bytes(b'synthetic')
    return root, tmp_path/'private-state'


@pytest.mark.parametrize('root', [pilot.PRODUCTION, pilot.PRODUCTION/'appdata',pilot.PRODUCTION.parent,Path('/data/test')])
def test_native_pilot_refuses_production_overlap(tmp_path,root):
    with pytest.raises(ValueError,match='production'):
        pilot.validate_paths(root,tmp_path/'state')


def test_native_pilot_rejects_symlink_escape(tmp_path):
    root,state=data_copy(tmp_path)
    (root/'outside').symlink_to(tmp_path/'other')
    with pytest.raises(ValueError,match='symlinks'):
        pilot.validate_paths(root,state)


def test_native_pilot_requires_matching_marker_and_private_auth(tmp_path):
    root,state=data_copy(tmp_path)
    pilot.initialize(root,state,'synthetic pilot password')
    assert pilot.check_initialized(root,state)==(root.resolve(),state.resolve())
    assert 'synthetic pilot password' not in (state/'passphrase.json').read_text()
    (state/'passphrase.json').chmod(0o644)
    with pytest.raises(ValueError,match='authentication'):
        pilot.check_initialized(root,state)


def test_native_pilot_marker_is_bound_to_copy(tmp_path):
    root,state=data_copy(tmp_path)
    pilot.initialize(root,state,'synthetic pilot password')
    marker=json.loads((root/pilot.MARKER).read_text())
    marker['data_root']=str(tmp_path/'different')
    (root/pilot.MARKER).write_text(json.dumps(marker))
    with pytest.raises(ValueError,match='marker'):
        pilot.check_initialized(root,state)


def test_native_pilot_never_overwrites_initialization(tmp_path):
    root,state=data_copy(tmp_path)
    pilot.initialize(root,state,'synthetic pilot password')
    before=(state/'passphrase.json').read_bytes()
    with pytest.raises(ValueError,match='Already'):
        pilot.initialize(root,state,'different pilot password')
    assert (state/'passphrase.json').read_bytes()==before


def test_native_pilot_password_rotation_keeps_data_and_voice_secret(tmp_path):
    root,state=data_copy(tmp_path)
    pilot.initialize(root,state,'synthetic pilot password')
    before=(state/'passphrase.json').read_bytes()
    voice=(state/'voice-bridge-token.json').read_bytes()
    (state/'auth_tokens.json').write_text('{"tokens":[{"old":"session"}]}')
    pilot.rotate_passphrase(root,state,'new synthetic pilot password')
    assert (state/'passphrase.json').read_bytes()!=before
    assert (state/'voice-bridge-token.json').read_bytes()==voice
    assert json.loads((state/'auth_tokens.json').read_text()) == {'tokens':[]}
    assert (root/'appdata/chroma/chroma.sqlite3').read_bytes()==b'synthetic'
    assert pilot.check_initialized(root,state)


@pytest.mark.parametrize('origin',[
    'http://test.tailnet.ts.net:8443','https://test.tailnet.ts.net',
    'https://test.tailnet.ts.net:443','https://example.com:8443',
    'https://test.tailnet.ts.net:8443/','https://user@test.tailnet.ts.net:8443',
    'https://test.tailnet.ts.net:8443?x=1','https://test.tailnet.ts.net:8443#test',
    'https://test.tailnet.ts.net.evil.example:8443',
])
def test_native_pilot_rejects_nonisolated_https_origins(origin):
    with pytest.raises(ValueError):
        pilot.validate_pilot_origin(origin)


def test_native_pilot_exact_https_origin_and_separate_cookie(tmp_path):
    root,state=data_copy(tmp_path)
    origin='https://test.tailnet.ts.net:8443'
    settings=pilot.settings_for(root,state,8792,origin)
    assert settings['trusted_hosts']=='127.0.0.1,localhost,test.tailnet.ts.net'
    assert settings['cors_origins']=='http://127.0.0.1:8792,'+origin
    assert pilot.PILOT_COOKIE != 'here_i_am_session'


def test_native_pilot_settings_ignore_cloud_keys_and_original_paths(tmp_path,monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY','must-not-be-used')
    root,state=data_copy(tmp_path)
    values=pilot.settings_for(root,state,8792)
    assert values['openai_api_key']==''
    assert values['openai_api_key_file']==''
    assert values['voice_host_data_root']==str(root)
    assert values['auth_tokens_path']==str(state/'auth_tokens.json')
    for name,value in values.items():
        if name.endswith(('_dir','_path','_file')) and value:
            assert Path(value).is_relative_to(root) or Path(value).is_relative_to(state)


def test_native_pilot_limits_mutations():
    for path in ['/api/auth/login','/api/recordings/upload','/api/sessions/synthetic-id/recording/retry']:
        assert pilot.mutation_allowed('POST',path)
    for path in ['/api/voice/speak','/api/memory-batch/start','/api/ollama/start','/api/chat','/api/speakers']:
        assert not pilot.mutation_allowed('POST',path)
    assert not pilot.mutation_allowed('DELETE','/api/sessions/example')


def test_native_pilot_voice_opt_in_is_narrow():
    assert pilot.mutation_allowed('POST','/api/voice/speak',voice_enabled=True)
    assert pilot.mutation_allowed('POST','/api/voice/cancel/test-1',voice_enabled=True)
    for path in ['/api/voice/revoke','/api/voice/prepare','/api/voice/cache/clear','/api/chat','/api/voice/cancel/../escape']:
        assert not pilot.mutation_allowed('POST',path,voice_enabled=True)


def test_native_pilot_voice_requires_private_token(tmp_path):
    root,state=data_copy(tmp_path)
    pilot.initialize(root,state,'synthetic pilot password')
    (state/'voice-bridge-token.json').chmod(0o644)
    with pytest.raises(ValueError,match='private'):
        pilot.voice_settings(root,state)


def test_native_pilot_voice_refuses_cloud_reference(tmp_path):
    root,state=data_copy(tmp_path)
    pilot.initialize(root,state,'synthetic pilot password')
    (root/'appdata/voice').mkdir()
    (root/'appdata/voice/voice_status.json').write_text(json.dumps({'provider':'elevenlabs','consented':True,'enabled':True}))
    with pytest.raises(ValueError,match='local voice'):
        pilot.voice_settings(root,state)


@pytest.mark.parametrize('value',[{}, {'algorithm':'bad'}, {'algorithm':'pbkdf2_sha256','iterations':600000,'salt':None,'hash':None}])
def test_native_pilot_invalid_auth_fails_closed(tmp_path,value):
    path=tmp_path/'passphrase.json'
    path.write_text(json.dumps(value))
    path.chmod(0o600)
    assert not pilot.auth_record_valid(path)


def test_native_pilot_port_check_rejects_live_listener():
    with socket.socket() as listener:
        listener.setsockopt(socket.SOL_SOCKET,socket.SO_REUSEADDR,1)
        listener.bind(('127.0.0.1',0))
        listener.listen()
        port=listener.getsockname()[1]
        with pytest.raises(OSError):
            pilot.check_port(port)
    pilot.check_port(port)
