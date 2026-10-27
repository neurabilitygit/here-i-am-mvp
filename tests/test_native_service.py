import importlib.util
import json
import os
from pathlib import Path
import sys

import pytest


def module(name):
    scripts=Path(__file__).resolve().parents[1]/'scripts'
    sys.path.insert(0,str(scripts))
    try:
        spec=importlib.util.spec_from_file_location(name,scripts/(name+'.py'))
        loaded=importlib.util.module_from_spec(spec); spec.loader.exec_module(loaded)
        return loaded
    finally:
        sys.path.remove(str(scripts))


def test_pilot_launchd_definition_is_scoped_and_has_no_secrets(tmp_path):
    service=module('native_service')
    profile={'source_root':str(tmp_path/'release'),'state_dir':str(tmp_path/'private'),
             'backend_python':'/safe/native/bin/python','voice_python':'/safe/voice/bin/python',
             'data_root':str(tmp_path/'copy'),'model_path':'/safe/cached-model',
             'pilot_origin':'https://test.tailnet.ts.net:8443'}
    plist=service.build_plist(profile)
    assert plist['Label']=='org.hereiam.native-pilot'
    assert plist['KeepAlive']=={'SuccessfulExit':False}
    assert plist['AbandonProcessGroup'] is False
    assert plist['ThrottleInterval']==30 and plist['ExitTimeOut']==45
    assert plist['Umask']==0o077
    assert not any('TOKEN' in k or 'KEY' in k for k in plist['EnvironmentVariables'])
    assert all('8787' not in item and '8779' not in item for item in plist['ProgramArguments'])


@pytest.mark.parametrize('bad',['data/release','state/release','/Volumes/Personal/here-i-am/release','/data/release'])
def test_bundle_refuses_storage_overlap(tmp_path,bad):
    service=module('native_service')
    bundle=tmp_path/bad
    with pytest.raises(ValueError,match='separate'):
        service.validate_bundle_destination(bundle,bundle/'profile.json',tmp_path/'data',tmp_path/'state')


def test_bundle_refuses_profile_escape(tmp_path):
    service=module('native_service')
    with pytest.raises(ValueError,match='inside'):
        service.validate_bundle_destination(tmp_path/'bundle',tmp_path/'elsewhere.json',tmp_path/'data',tmp_path/'state')


def test_release_tampering_is_refused(tmp_path):
    service=module('native_service')
    path=tmp_path/'file'; path.write_text('reviewed source')
    (tmp_path/'release-manifest.json').write_text(json.dumps({'commit':'synthetic','files':{'file':service.checksum(path)}}))
    assert service.verify_release(tmp_path)=='synthetic'
    path.write_text('changed')
    with pytest.raises(ValueError,match='integrity'):
        service.verify_release(tmp_path)


def test_release_extra_files_are_refused(tmp_path):
    service=module('native_service')
    path=tmp_path/'file'; path.write_text('reviewed source')
    (tmp_path/'release-manifest.json').write_text(json.dumps({'commit':'synthetic','files':{'file':service.checksum(path)}}))
    (tmp_path/'unexpected').write_text('not packaged')
    with pytest.raises(ValueError,match='inventory'):
        service.verify_release(tmp_path)


def test_supervisor_lock_rejects_duplicate_and_releases(tmp_path):
    supervisor=module('run_native_phone_pilot')
    with supervisor.supervisor_lock(tmp_path):
        with pytest.raises(RuntimeError,match='already'):
            with supervisor.supervisor_lock(tmp_path):
                pass
    with supervisor.supervisor_lock(tmp_path):
        assert (tmp_path/'supervisor.lock').stat().st_mode & 0o777==0o600


def test_supervisor_status_does_not_contain_credentials(tmp_path):
    supervisor=module('run_native_phone_pilot')
    supervisor.write_status(tmp_path,'ready',[],source_root='/safe/release')
    value=json.loads((tmp_path/'service-status.json').read_text())
    assert value['phase']=='ready' and value['supervisor_pid']==os.getpid()
    assert (tmp_path/'service-status.json').stat().st_mode & 0o777==0o600


def test_health_probe_does_not_treat_bad_body_as_ready():
    supervisor=module('run_native_phone_pilot')
    class BadResponse:
        ok=True
        def json(self): return {'status':'error'}
    class Client:
        def get(self,*args,**kwargs): return BadResponse()
    assert supervisor.service_health(Client()) is False
