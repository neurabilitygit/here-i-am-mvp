import importlib.util
import json
from pathlib import Path
import sys

import pytest


def module():
    scripts=Path(__file__).resolve().parents[1]/'scripts'
    sys.path.insert(0,str(scripts))
    try:
        spec=importlib.util.spec_from_file_location('native_deployment',scripts/'native_deployment.py')
        result=importlib.util.module_from_spec(spec); spec.loader.exec_module(result)
        return result
    finally: sys.path.remove(str(scripts))


def profile(tmp_path):
    root=tmp_path/'copy'; state=tmp_path/'state'; state.mkdir(mode=0o700)
    (root/'library/sessions').mkdir(parents=True)
    (root/'appdata/chroma').mkdir(parents=True)
    (root/'appdata/chroma/chroma.sqlite3').write_bytes(b'synthetic')
    auth=state/'auth.json'
    auth.write_text(json.dumps({'algorithm':'pbkdf2_sha256','iterations':600000,'salt':'ab'*16,'hash':'cd'*32}))
    auth.chmod(0o600)
    token=state/'bridge'; token.write_text('synthetic-token-'*4); token.chmod(0o600)
    return {'schema':1,'kind':'staging','data_root':str(root),'state_dir':str(state),
            'bridge_token_file':str(token),'settings':{'auth_passphrase_hash_file':str(auth)},
            'source_root':str(tmp_path/'release'),'source_commit':'reviewed','source_date':'today',
            'backend_python':'/durable/bin/python'}


def test_staging_cannot_use_production_data(tmp_path,monkeypatch):
    m=module(); p=profile(tmp_path)
    monkeypatch.setattr(m,'PRODUCTION',Path(p['data_root']))
    with pytest.raises(ValueError,match='Staging'): m.validate_storage(p)


def test_production_cannot_silently_change_storage_location(tmp_path):
    m=module(); p=profile(tmp_path); p['kind']='production'
    with pytest.raises(ValueError,match='existing data'): m.validate_storage(p)


def test_missing_database_does_not_create_replacement(tmp_path):
    m=module(); p=profile(tmp_path)
    db=Path(p['data_root'])/'appdata/chroma/chroma.sqlite3'
    db.rename(db.with_suffix('.retained'))
    with pytest.raises(ValueError,match='refusing empty'): m.validate_storage(p)
    assert not db.exists()


def test_missing_authentication_fails_closed(tmp_path):
    m=module(); p=profile(tmp_path)
    p['settings']['auth_passphrase_hash_file']=str(tmp_path/'unavailable')
    with pytest.raises(ValueError,match='passphrase'): m.validate_storage(p)


def test_staging_maps_every_runtime_path_and_disables_cloud(tmp_path):
    m=module(); p=profile(tmp_path)
    p['settings'].update(openai_api_key_file='/production/secret',speaker_diarization_provider='openai',
                         data_root='/data',chroma_dir='/data/appdata/chroma',voice_host_data_root='/production')
    values=m.application_settings(p)
    assert values['openai_api_key_file']=='' and values['speaker_diarization_provider']=='disabled'
    assert values['chroma_dir']==str(Path(p['data_root'])/'appdata/chroma')
    assert values['auth_tokens_path']==str(Path(p['data_root'])/'appdata/auth_tokens.json')
    assert values['voice_host_data_root']==p['data_root']
    assert values['locks_dir']==str(Path(p['state_dir'])/'locks')
    assert values['voice_bridge_url']=='http://127.0.0.1:8795'
    assert values['ollama_control_url']=='http://127.0.0.1:8796'


@pytest.mark.parametrize('key',['openai_api_key','elevenlabs_api_key','local_bridge_token'])
def test_profile_refuses_embedded_secret_values(tmp_path,key):
    m=module(); p=profile(tmp_path); p['settings'][key]='must-be-file-backed'
    path=tmp_path/'profile.json'; path.write_text(json.dumps(p)); path.chmod(0o600)
    with pytest.raises(ValueError,match='secret values'): m.load_profile(path)


def test_production_and_pilot_services_are_separate(tmp_path):
    m=module(); p=profile(tmp_path)
    staging=m.build_plist(p,tmp_path/'staging.json'); p['kind']='production'
    production=m.build_plist(p,tmp_path/'production.json')
    assert staging['Label']=='org.hereiam.native-staging'
    assert production['Label']=='org.hereiam.native-production'
    assert production['KeepAlive']=={'SuccessfulExit':False}
    assert production['AbandonProcessGroup'] is False
    assert 'LOCAL_BRIDGE_TOKEN' not in production['EnvironmentVariables']
    assert m.PORTS['production']==(8787,8779,8778)


def test_duplicate_native_supervisor_refused(tmp_path):
    m=module()
    with m.owner_lock(tmp_path):
        with pytest.raises(RuntimeError,match='already supervised'):
            with m.owner_lock(tmp_path): pass


def test_stop_waits_for_job_and_listeners_without_reading_data(tmp_path,monkeypatch):
    from types import SimpleNamespace
    m=module(); p={'schema':1,'kind':'staging','settings':{}}
    path=tmp_path/'profile.json'; path.write_text(json.dumps(p)); path.chmod(0o600)
    calls=[]; prints=iter([0,1,1]); ports=iter([False,True])
    def run(args,**kwargs):
        calls.append(args)
        return SimpleNamespace(returncode=next(prints) if 'print' in args else 0)
    monkeypatch.setattr(m.subprocess,'run',run)
    monkeypatch.setattr(m,'ports_available',lambda _p:next(ports))
    monkeypatch.setattr(m.time,'sleep',lambda _n:None)
    monkeypatch.setattr(sys,'argv',['native_deployment.py','stop','--profile',str(path)])
    m.main()
    assert sum('print' in call for call in calls)==3
