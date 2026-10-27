#!/usr/bin/env python3
"""Supervise the isolated native phone pilot. Never changes VPN or production.

Use daemonize.py to leave this running for a manual device test. Terminating
this supervisor stops only the two children it created. No data is removed.
"""
import argparse
import json
import os
from pathlib import Path
import signal
import subprocess
import sys
import time

import requests

from native_pilot import REPO, check_initialized, check_port, check_runtime, validate_pilot_origin


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--voice-python',type=Path,required=True)
    p.add_argument('--model-path',type=Path,required=True)
    p.add_argument('--pilot-origin',required=True)
    args=p.parse_args()
    root,state=check_initialized(args.data_root,args.state_dir)
    validate_pilot_origin(args.pilot_origin)
    check_runtime(); check_port(8792); check_port(8793)
    model=args.model_path.resolve()
    if not (model/'config.json').is_file() or not list(model.glob('*.safetensors')):
        raise ValueError('An already downloaded MLX model snapshot is required')
    if not (state/'local-clone-test.wav').is_file():
        raise ValueError('Run isolated voice acceptance before the physical phone test')
    token_file=state/'voice-bridge-token.json'
    if token_file.stat().st_mode & 0o777 != 0o600:
        raise ValueError('Pilot bridge token is not private')
    token=json.loads(token_file.read_text())['token']
    env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','PYTHONDONTWRITEBYTECODE':'1',
        'HF_HUB_OFFLINE':'1','TRANSFORMERS_OFFLINE':'1','APP_BUILD_COMMIT':'native-voice-pilot',
        'HERE_I_AM_VOICE_DATA_ROOT':str(root),'LOCAL_BRIDGE_TOKEN':token,
        'QWEN_TTS_MLX_MODEL':str(model),'QWEN_TTS_MODEL_REVISION':model.name,
        'QWEN_TTS_CACHE_DIR':str(state/'voice-cache'),'QWEN_TTS_SENTENCE_BATCH_SIZE':'4',
        'QWEN_TTS_MODEL_IDLE_SECONDS':'120'}
    children=[]
    def interrupted(_signum,_frame):
        raise KeyboardInterrupt
    signal.signal(signal.SIGTERM,interrupted)
    signal.signal(signal.SIGINT,interrupted)
    client=requests.Session(); client.trust_env=False
    with (state/'phone-voice.log').open('a') as voice_log,(state/'phone-backend.log').open('a') as app_log:
        def start(command,log,url,environment):
            process=subprocess.Popen(command,env=environment,stdin=subprocess.DEVNULL,stdout=log,stderr=log,cwd=REPO)
            children.append(process)
            for _ in range(200):
                if process.poll() is not None:
                    raise RuntimeError('Pilot service failed; inspect its private log')
                try:
                    if client.get(url,timeout=.5).ok:
                        return
                except requests.RequestException:
                    pass
                time.sleep(.1)
            raise RuntimeError('Pilot startup timed out')
        try:
            start([str(args.voice_python),'-m','uvicorn','scripts.mlx_voice_bridge:app','--app-dir',str(REPO),
                   '--host','127.0.0.1','--port','8793','--no-access-log'],voice_log,'http://127.0.0.1:8793/health',env)
            start([sys.executable,str(REPO/'scripts/native_pilot.py'),'run','--data-root',str(root),
                   '--state-dir',str(state),'--enable-local-voice','--pilot-origin',args.pilot_origin],
                  app_log,'http://127.0.0.1:8792/api/health',{'PATH':env['PATH'],'PYTHONDONTWRITEBYTECODE':'1'})
            print(json.dumps({'ready':True,'pid':os.getpid(),'origin':args.pilot_origin,'production_changed':False}),flush=True)
            while all(process.poll() is None for process in children):
                time.sleep(1)
            raise RuntimeError('A pilot child exited; stopping the other child')
        except KeyboardInterrupt:
            pass
        finally:
            for process in reversed(children):
                if process.poll() is None:
                    process.terminate()
                    try: process.wait(timeout=15)
                    except subprocess.TimeoutExpired:
                        process.kill(); process.wait(timeout=5)


if __name__=='__main__':
    main()
