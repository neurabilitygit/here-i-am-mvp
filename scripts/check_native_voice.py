#!/usr/bin/env python3
"""Explicit local clone acceptance on a fresh isolated pilot copy.

Reuses installed MLX packages and a local model snapshot offline. Does not
restart production bridges, alter original references, or send text to cloud.
"""
import argparse
from concurrent.futures import ThreadPoolExecutor
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import time
import wave

import requests

from native_pilot import REPO, VOICE_TEST_TEXT, check_port, check_runtime, initialize, validate_paths

TEXT=VOICE_TEST_TEXT


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--voice-python',type=Path,required=True)
    p.add_argument('--model-path',type=Path,required=True)
    p.add_argument('--confirm-local-clone-test',action='store_true',required=True)
    args=p.parse_args()
    root,state=validate_paths(args.data_root,args.state_dir)
    check_runtime(); check_port(8792); check_port(8793)
    model=args.model_path.resolve()
    if not (model/'config.json').is_file() or not list(model.glob('*.safetensors')):
        raise ValueError('An already downloaded MLX model snapshot is required')
    client=requests.Session(); client.trust_env=False
    def production_idle():
        health=client.get('http://127.0.0.1:8779/health',timeout=5).json()
        models=client.get('http://127.0.0.1:11434/api/ps',timeout=5).json()['models']
        if health.get('busy') or health.get('model_loaded') or models:
            raise RuntimeError('Production inference is not idle; defer the pilot')
    production_idle()
    password=secrets.token_urlsafe(32)
    initialize(root,state,password)
    token=json.loads((state/'voice-bridge-token.json').read_text())['token']
    headers={'X-Here-I-Am-Local':token}
    reference=root/'appdata/voice/voice_reference.wav'
    reference_text=root/'appdata/voice/voice_reference.txt'
    hashes={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in [reference,reference_text]}
    env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','PYTHONDONTWRITEBYTECODE':'1',
        'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','APP_BUILD_COMMIT':'native-voice-pilot',
        'HERE_I_AM_VOICE_DATA_ROOT':str(root),'LOCAL_BRIDGE_TOKEN':token,
        'QWEN_TTS_MLX_MODEL':str(model),'QWEN_TTS_MODEL_REVISION':model.name,
        'QWEN_TTS_CACHE_DIR':str(state/'voice-cache'),'QWEN_TTS_SENTENCE_BATCH_SIZE':'4',
        'QWEN_TTS_MODEL_IDLE_SECONDS':'120'}
    processes=[]
    report={}
    with (state/'voice-bridge.log').open('w') as voice_log,(state/'backend.log').open('w') as app_log:
        def start(command,log,url,environment=None):
            process=subprocess.Popen(command,env=environment,stdout=log,stderr=log)
            processes.append(process)
            for _ in range(200):
                if process.poll() is not None:
                    raise RuntimeError('Pilot service failed; inspect its private log')
                try:
                    if client.get(url,timeout=.5).ok:
                        return process
                except requests.RequestException:
                    pass
                time.sleep(.1)
            raise RuntimeError('Pilot service startup timed out')
        try:
            start([str(args.voice_python),'-m','uvicorn','scripts.mlx_voice_bridge:app','--app-dir',str(REPO),
                   '--host','127.0.0.1','--port','8793','--no-access-log'],voice_log,'http://127.0.0.1:8793/health',env)
            bridge='http://127.0.0.1:8793'
            assert client.post(bridge+'/auth/check',timeout=5).status_code==403
            assert client.post(bridge+'/auth/check',headers=headers,timeout=5).status_code==200
            assert client.post(bridge+'/synthesize',headers=headers,json={'text':'Boundary test','reference_audio':'/Volumes/Personal/here-i-am/appdata/voice/voice_reference.wav'},timeout=5).status_code==403
            app='http://127.0.0.1:8792'
            start([sys.executable,str(REPO/'scripts/native_pilot.py'),'run','--data-root',str(root),
                   '--state-dir',str(state),'--enable-local-voice'],app_log,app+'/api/health')
            assert client.post(app+'/api/auth/login',json={'passphrase':password},timeout=5).status_code==200
            status=client.get(app+'/api/voice/status',timeout=5).json()
            assert status['provider']=='local' and status['bridge_ready'] and status['reference_ready']
            production_idle()
            print('Generating one complete cloned-voice WAV locally...',flush=True)
            start_time=time.perf_counter()
            response=client.post(app+'/api/voice/speak',json={'text':TEXT,'speed':1.0,'request_id':'pilot-complete'},timeout=155)
            elapsed=time.perf_counter()-start_time
            if response.status_code!=200:
                raise RuntimeError(f'Voice generation failed with HTTP {response.status_code}; inspect private logs')
            assert response.headers['X-Voice-Provider']=='local'
            with wave.open(BytesIO(response.content),'rb') as audio:
                duration=audio.getnframes()/audio.getframerate()
                frames=audio.readframes(audio.getnframes())
                assert duration>1 and len(set(frames))>2
            (state/'local-clone-test.wav').write_bytes(response.content)
            start_time=time.perf_counter()
            cached=client.post(app+'/api/voice/speak',json={'text':TEXT,'speed':1.0,'request_id':'pilot-cached'},timeout=10)
            cache_seconds=time.perf_counter()-start_time
            assert cached.status_code==200 and cached.content==response.content
            report.update(complete_wav=True,audio_seconds=duration,first_request_seconds=elapsed,
                repeated_request_seconds=cache_seconds,repeated_audio_identical=True,
                voice_file=str(state/'local-clone-test.wav'),boundary_checks=True)
            (state/'voice-acceptance.json').write_text(json.dumps(report,indent=2))
            browser=subprocess.run(['node',str(REPO/'scripts/check_native_voice_browser.cjs')],
                input=json.dumps({'passphrase':password,'text':TEXT}),capture_output=True,text=True,timeout=75)
            if browser.returncode:
                raise RuntimeError('Voice browser acceptance failed: '+browser.stderr[-1500:])
            report['browser']=json.loads(browser.stdout)
            # Verify active-job unload refusal and cancellation using a new text.
            production_idle()
            with ThreadPoolExecutor(max_workers=1) as pool:
                pending=pool.submit(client.post,app+'/api/voice/speak',json={'text':TEXT+' This separate request tests cancellation safely.','request_id':'pilot-cancel'},timeout=155)
                for _ in range(100):
                    if client.get(bridge+'/health',timeout=5).json()['busy']:
                        break
                    if pending.done():
                        raise RuntimeError('Cancellation fixture finished before becoming observable')
                    time.sleep(.05)
                assert client.post(bridge+'/model/unload',headers=headers,timeout=5).status_code==409
                start_time=time.perf_counter()
                assert client.post(app+'/api/voice/cancel/pilot-cancel',timeout=5).status_code==200
                canceled=pending.result(timeout=30)
                report['cancellation_seconds']=time.perf_counter()-start_time
                assert canceled.status_code!=200
                assert client.get(bridge+'/health',timeout=5).json()['busy'] is False
            assert client.post(bridge+'/model/unload',headers=headers,timeout=10).status_code==200
            assert client.get(bridge+'/health',timeout=5).json()['model_loaded'] is False
            assert all(hashlib.sha256(Path(p).read_bytes()).hexdigest()==h for p,h in hashes.items())
            report.update(cancellation_releases_job=True,idle_model_unloaded=True,reference_files_unchanged=True,passed=True)
            (state/'voice-acceptance.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2))
        finally:
            for process in reversed(processes):
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=5)


if __name__=='__main__':
    main()
