#!/usr/bin/env python3
"""Full native deployment, separate from the deliberately restricted pilot.

Profiles contain paths/settings, never secret values. No storage is moved,
database record deleted, VPN route reset, or model downloaded by this launcher.
"""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import fcntl
import json
import os
from pathlib import Path
import plistlib
import signal
import stat
import subprocess
import sys
import time

import requests

from native_pilot import PRODUCTION, auth_record_valid, check_port, check_runtime
from native_service import verify_release

PORTS={'staging':(8794,8795,8796),'production':(8787,8779,8778)}
ENV={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
     'PYTHONDONTWRITEBYTECODE':'1','HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1',
     'ANONYMIZED_TELEMETRY':'False','OTEL_SDK_DISABLED':'true'}


def load_profile(path):
    if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode)!=0o600:
        raise ValueError('A private regular deployment profile is required')
    p=json.loads(path.read_text())
    if p.get('schema')!=1 or p.get('kind') not in PORTS:
        raise ValueError('Unknown native deployment profile')
    if any(p.get('settings',{}).get(key) for key in ('openai_api_key','elevenlabs_api_key','local_bridge_token')):
        raise ValueError('Profiles must not contain secret values')
    return p


def label(p): return 'org.hereiam.native-'+p['kind']
def target(p): return f'gui/{os.getuid()}/{label(p)}'


def ports_available(p):
    try:
        for port in PORTS[p['kind']]: check_port(port)
        return True
    except OSError: return False


def validate_storage(p):
    root=Path(p['data_root']).resolve(); state=Path(p['state_dir']).resolve()
    if p['kind']=='production' and root!=PRODUCTION.resolve():
        raise ValueError('Production must retain its existing data location')
    if p['kind']=='staging' and (root==PRODUCTION.resolve() or PRODUCTION.resolve() in root.parents or root in PRODUCTION.resolve().parents):
        raise ValueError('Staging must not use production storage')
    if root==state or root in state.parents or state in root.parents:
        raise ValueError('Private state and library must be separate')
    if not (root/'library/sessions').is_dir() or not (root/'appdata/chroma/chroma.sqlite3').is_file():
        raise ValueError('Existing library/database unavailable; refusing empty replacement storage')
    if not state.is_dir() or stat.S_IMODE(state.stat().st_mode)!=0o700:
        raise ValueError('Private state directory must already exist with mode 700')
    if not auth_record_valid(Path(p['settings']['auth_passphrase_hash_file'])):
        raise ValueError('Existing passphrase is unavailable or invalid')
    for key in ('bridge_token_file',):
        path=Path(p[key])
        if path.is_symlink() or not path.is_file() or stat.S_IMODE(path.stat().st_mode)!=0o600:
            raise ValueError('Protected bridge credential is unavailable')
    if len(Path(p['bridge_token_file']).read_text().strip())<32:
        raise ValueError('Protected bridge credential is invalid')
    return root,state


def application_settings(p):
    root,state=validate_storage(p)
    port,voice,control=PORTS[p['kind']]
    paths={'sessions_dir':'library/sessions','archive_dir':'library/archive','chroma_dir':'appdata/chroma',
           'logs_dir':'appdata/logs','tmp_dir':'appdata/tmp','jobs_dir':'appdata/jobs','exports_dir':'appdata/exports',
           'preferences_path':'appdata/preferences.json','fidelity_profile_path':'appdata/speaker_fingerprint.json',
           'feedback_path':'appdata/answer_feedback.jsonl','generation_audit_path':'appdata/generation_audit.jsonl',
           'activity_event_path':'appdata/logs/activity_events.jsonl','voice_dir':'appdata/voice','speakers_dir':'appdata/speakers',
           'auth_tokens_path':'appdata/auth_tokens.json'}
    values=dict(p['settings'])
    values.update({k:str(root/v) for k,v in paths.items()})
    values.update(data_root=str(root),voice_host_data_root=str(root),locks_dir=str(state/'locks'),
                  local_workload_lock_path=str(state/'inference.lock'),host='127.0.0.1',port=port,
                  ollama_base_url='http://127.0.0.1:11434',ollama_control_url=f'http://127.0.0.1:{control}',
                  voice_bridge_url=f'http://127.0.0.1:{voice}',voice_provider='local',
                  local_bridge_token=Path(p['bridge_token_file']).read_text().strip(),
                  app_build_commit=p['source_commit'],app_build_date=p['source_date'],
                  openai_api_key='',elevenlabs_api_key='',allow_runtime_cloud_key=False)
    if p['kind']=='staging':
        values.update(cors_origins=f'http://127.0.0.1:{port}',trusted_hosts='127.0.0.1,localhost',
                      openai_api_key_file='',openai_base_url='http://127.0.0.1:1',speaker_diarization_provider='disabled')
    return values


def validate_profile(p):
    root,state=validate_storage(p)
    source=Path(p['source_root'])
    if verify_release(source)!=p['source_commit']:
        raise ValueError('Source release does not match deployment profile')
    python=Path(p['backend_python'])
    if not python.is_absolute() or not python.is_file() or str(python).startswith(('/tmp/','/private/tmp/')):
        raise ValueError('A durable native runtime is required')
    subprocess.run([str(python),'-c','from native_pilot import check_runtime; check_runtime()'],
                   env={**ENV,'PYTHONPATH':str(source/'scripts')},cwd=state,check=True,timeout=30)
    if not Path(p['voice_python']).is_file() or not (Path(p['model_path'])/'config.json').is_file():
        raise ValueError('Local voice runtime/model is unavailable')
    return root,state


def write_status(state,phase,children,**extra):
    path=state/f'.status-{os.getpid()}.tmp'
    with path.open('w') as f:
        os.chmod(path,0o600)
        json.dump({'phase':phase,'pid':os.getpid(),'children':{name:c.pid for name,c in children},
                   'updated_at':datetime.now(timezone.utc).isoformat(),**extra},f,indent=2)
        f.flush(); os.fsync(f.fileno())
    os.replace(path,state/'service-status.json')


@contextmanager
def owner_lock(state):
    with (state/'supervisor.lock').open('a') as handle:
        os.chmod(handle.name,0o600)
        try: fcntl.flock(handle,fcntl.LOCK_EX|fcntl.LOCK_NB)
        except BlockingIOError as exc: raise RuntimeError('Deployment already supervised') from exc
        yield


def build_plist(p,profile_path):
    source=Path(p['source_root']); state=Path(p['state_dir'])
    return {'Label':label(p),'ProgramArguments':[p['backend_python'],str(source/'scripts/native_deployment.py'),
            'supervise','--profile',str(profile_path)],'WorkingDirectory':str(source),
            'RunAtLoad':True,'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':30,
            'ExitTimeOut':60,'AbandonProcessGroup':False,'ProcessType':'Background','Umask':0o077,
            'EnvironmentVariables':ENV,'StandardOutPath':str(state/'supervisor.log'),
            'StandardErrorPath':str(state/'supervisor-error.log')}


def run_application(p):
    check_runtime()
    values=application_settings(p)
    check_port(PORTS[p['kind']][0])
    source=Path(p['source_root'])
    os.environ.clear(); os.environ.update(ENV)
    os.chdir(p['state_dir']); sys.path.insert(0,str(source/'app'))
    import config
    config.settings=config.Settings(_env_file=None,**values)
    if p['kind']=='staging':
        from services import auth
        auth.SESSION_COOKIE_NAME='here_i_am_staging_session'
    from main import app
    from starlette.responses import JSONResponse
    import uvicorn
    @app.middleware('http')
    async def storage_and_auth_guard(request,call_next):
        # Avoid fail-open auth or recreating an empty library if the drive goes away.
        if not auth_record_valid(Path(values['auth_passphrase_hash_file'])) or not Path(values['chroma_dir'],'chroma.sqlite3').is_file():
            return JSONResponse({'detail':'Protected storage or authentication is unavailable'},status_code=503)
        return await call_next(request)
    uvicorn.run(app,host='127.0.0.1',port=values['port'],access_log=False,limit_concurrency=32)


def supervise(p,profile_path):
    root,state=validate_profile(p)
    with owner_lock(state):
        for port in PORTS[p['kind']]: check_port(port)
        children=[]; logs=[]; phase='starting'
        session=requests.Session(); session.trust_env=False
        def ok(url):
            try: return session.get(url,timeout=2).ok
            except requests.RequestException: return False
        def interrupted(*_): raise KeyboardInterrupt
        signal.signal(signal.SIGTERM,interrupted); signal.signal(signal.SIGINT,interrupted)
        source=Path(p['source_root']); app_port,voice_port,control_port=PORTS[p['kind']]
        voice_env={**ENV,'LOCAL_BRIDGE_TOKEN':Path(p['bridge_token_file']).read_text().strip(),
                   'APP_BUILD_COMMIT':p['source_commit'],'HERE_I_AM_VOICE_DATA_ROOT':str(root),
                   'QWEN_TTS_MLX_MODEL':p['model_path'],'QWEN_TTS_MODEL_REVISION':Path(p['model_path']).name,
                   'QWEN_TTS_CACHE_DIR':str(root/'appdata/voice/cache'),'QWEN_TTS_MODEL_IDLE_SECONDS':'120',
                   'QWEN_TTS_SENTENCE_BATCH_SIZE':'4','OLLAMA_MODELS':p['ollama_models'],
                   'OLLAMA_PID_FILE':p['ollama_pid_file'],'OLLAMA_URL':'http://127.0.0.1:11434'}
        def start(name,command,url,env):
            logpath=state/(name+'.log')
            if logpath.exists() and logpath.stat().st_size>10*1024*1024:
                logpath.rename(state/(name+'.'+str(time.time_ns())+'.log'))
            log=logpath.open('a'); os.chmod(logpath,0o600); logs.append(log)
            process=subprocess.Popen(command,env=env,cwd=source,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
            children.append((name,process)); write_status(state,'starting',children,source_commit=p['source_commit'])
            for _ in range(90):
                if process.poll() is not None: raise RuntimeError(f'{name} exited during startup')
                if ok(url): return process
                time.sleep(1)
            raise RuntimeError(f'{name} startup timed out')
        try:
            if not ok('http://127.0.0.1:11434/api/tags'):
                process=start('ollama',['/opt/homebrew/bin/ollama','serve'],'http://127.0.0.1:11434/api/tags',voice_env)
                Path(p['ollama_pid_file']).write_text(str(process.pid))
            start('voice',[p['voice_python'],'-m','uvicorn','scripts.mlx_voice_bridge:app','--app-dir',str(source),
                          '--host','127.0.0.1','--port',str(voice_port),'--no-access-log'],f'http://127.0.0.1:{voice_port}/health',voice_env)
            start('control',[p['voice_python'],'-m','uvicorn','scripts.ollama_control_bridge:app','--app-dir',str(source),
                            '--host','127.0.0.1','--port',str(control_port),'--no-access-log'],f'http://127.0.0.1:{control_port}/status',voice_env)
            start('app',[p['backend_python'],str(source/'scripts/native_deployment.py'),'run','--profile',str(profile_path)],
                  f'http://127.0.0.1:{app_port}/api/health',ENV)
            phase='ready'; failures=0
            while all(c.poll() is None for _,c in children):
                write_status(state,phase,children,source_commit=p['source_commit'],failed_probes=failures)
                time.sleep(15)
                healthy=all(ok(url) for url in (f'http://127.0.0.1:{app_port}/api/health',f'http://127.0.0.1:{voice_port}/health',f'http://127.0.0.1:{control_port}/status'))
                failures=0 if healthy else failures+1
                phase='ready' if healthy else 'degraded'
                if failures>=3: raise RuntimeError('Repeated native service health failure')
            raise RuntimeError('Native child exited; restarting the complete owned service group')
        except KeyboardInterrupt: phase='stopped'
        except BaseException:
            phase='failed'; raise
        finally:
            for _,child in reversed(children):
                if child.poll() is None:
                    child.terminate()
                    try: child.wait(timeout=15)
                    except subprocess.TimeoutExpired: child.kill(); child.wait(timeout=5)
            write_status(state,phase,children,source_commit=p['source_commit'])
            for log in logs: log.close()


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('command',choices=['check','run','supervise','start','stop','status'])
    parser.add_argument('--profile',type=Path,required=True)
    args=parser.parse_args(); p=load_profile(args.profile)
    if args.command=='run': return run_application(p)
    if args.command=='supervise': return supervise(p,args.profile)
    if args.command=='stop':
        subprocess.run(['/bin/launchctl','bootout',target(p)],check=True)
        # bootout acknowledges the request before children have necessarily
        # exited. Wait for both ownership and listeners before reporting stop.
        for _ in range(50):
            loaded=subprocess.run(['/bin/launchctl','print',target(p)],capture_output=True)
            if loaded.returncode!=0 and ports_available(p):
                print('Native service stopped; stored data and routes retained.'); return
            time.sleep(1)
        raise RuntimeError('Native service is still stopping; inspect status before restarting')
    if args.command=='status':
        result=subprocess.run(['/bin/launchctl','print',target(p)],capture_output=True,text=True)
        print(result.stdout if result.returncode==0 else 'Native service is not loaded.'); return
    validate_profile(p)
    if args.command=='check': print('Native source, runtime, authentication and storage verified.'); return
    loaded=subprocess.run(['/bin/launchctl','print',target(p)],capture_output=True)
    if loaded.returncode==0:
        if str(args.profile).encode() not in loaded.stdout or p['source_root'].encode() not in loaded.stdout:
            raise RuntimeError('Another native release is still loaded or stopping; wait for its confirmed stop')
        print('Native service is already loaded. Check readiness before use.'); return
    for port in PORTS[p['kind']]: check_port(port)
    plist=args.profile.with_suffix('.plist')
    if plist.exists():
        if plist.is_symlink() or plistlib.loads(plist.read_bytes())!=build_plist(p,args.profile):
            raise ValueError('Service definition differs from profile')
    else:
        with plist.open('xb') as f:
            os.chmod(plist,0o600); plistlib.dump(build_plist(p,args.profile),f)
    subprocess.run(['/bin/launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],check=True)
    print('Native service requested; confirm readiness before use.')


if __name__=='__main__': main()
