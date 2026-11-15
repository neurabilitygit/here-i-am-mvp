#!/usr/bin/env python3
"""Explicitly mutating acceptance test for an isolated copied library only.

Creates synthetic recordings, retains them, never deletes Chroma. Starts and
stops its own native server. Uses a random one-run passphrase, never logs it.
"""
import argparse
import base64
import hashlib
from io import BytesIO
import json
from pathlib import Path
import secrets
import subprocess
import sys
import time
import wave

import requests

from native_pilot import REPO, check_runtime, initialize, validate_paths


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--data-root',type=Path,required=True)
    parser.add_argument('--state-dir',type=Path,required=True)
    parser.add_argument('--confirm-pilot-mutations',action='store_true',required=True)
    args=parser.parse_args()
    root,state=validate_paths(args.data_root,args.state_dir)
    check_runtime()
    password=secrets.token_urlsafe(32)
    initialize(root,state,password)
    command=[sys.executable,str(REPO/'scripts/native_pilot.py'),'run','--data-root',str(root),'--state-dir',str(state)]
    url='http://127.0.0.1:8792'
    process=None
    report={}
    with (state/'acceptance-server.log').open('w') as log:
        def start():
            p=subprocess.Popen(command,stdout=log,stderr=log)
            for _ in range(100):
                if p.poll() is not None:
                    raise RuntimeError('Pilot startup failed; inspect private server log')
                try:
                    if requests.get(url+'/api/health',timeout=.5).status_code==200:
                        return p
                except requests.RequestException:
                    pass
                time.sleep(.1)
            p.terminate(); p.wait(timeout=10)
            raise RuntimeError('Pilot did not become healthy')
        try:
            process=start()
            client=requests.Session()
            assert client.get(url+'/api/sessions',timeout=5).status_code==401
            assert client.post(url+'/api/auth/login',json={'passphrase':'incorrect-test-passphrase'},timeout=5).status_code==401
            assert client.post(url+'/api/auth/login',json={'passphrase':password},timeout=5).status_code==200
            assert client.get(url+'/api/sessions',timeout=5).status_code==200
            assert client.post(url+'/api/activity-events',json={},headers={'Origin':'https://invalid.example'},timeout=5).status_code==403
            assert client.post(url+'/api/memory-batch/start',json={},timeout=5).status_code==403
            report['authentication_and_boundary_checks']=True
            audio=BytesIO()
            with wave.open(audio,'wb') as w:
                w.setnchannels(1); w.setsampwidth(2); w.setframerate(16000)
                w.writeframes(b'\0\0'*8000)
            payload=audio.getvalue()
            uploaded=client.post(url+'/api/recordings/upload',files={'file':('synthetic.wav',payload,'audio/wav')},data={'title':'Synthetic native upload acceptance'},timeout=30)
            assert uploaded.status_code==200
            session_id=uploaded.json()['session_id']
            session=root/'library/sessions'/session_id
            assert (session/'recording.source').read_bytes()==payload
            assert json.loads((session/'processing_state.json').read_text())['source_sha256']==hashlib.sha256(payload).hexdigest()
            # Only this newly created synthetic fixture is interrupted.
            (session/'recording.flac').rename(session/'synthetic-pre-retry.flac')
            state_path=session/'processing_state.json'
            saved=json.loads(state_path.read_text()); saved['upload_status']='validation_failed'
            state_path.write_text(json.dumps(saved))
            retry=client.post(url+f'/api/sessions/{session_id}/recording/retry',timeout=30)
            assert retry.status_code==200 and retry.json()['status']=='ready'
            assert (session/'recording.source').read_bytes()==payload
            assert (session/'recording.flac').is_file()
            report['upload_and_server_retry']=True
            # Real browser upload with a simulated network failure and reload.
            browser=subprocess.run(['node',str(REPO/'scripts/check_native_pilot_browser.cjs')],
                input=json.dumps({'url':url,'passphrase':password,'audio':base64.b64encode(payload).decode()}),
                capture_output=True,text=True,timeout=60)
            if browser.returncode:
                raise RuntimeError('Browser acceptance failed: '+browser.stderr[-1500:])
            report['browser']=json.loads(browser.stdout)
            secret=state/'passphrase.json'; saved_secret=state/'passphrase.saved'
            secret.rename(saved_secret)
            try:
                assert client.get(url+'/api/sessions',timeout=5).status_code==503
            finally:
                saved_secret.rename(secret)
            report['missing_auth_fails_closed']=True
            (state/'acceptance-report.json').write_text(json.dumps(report,indent=2))
            process.terminate(); process.wait(timeout=15); process=None
            process=start()
            sessions=client.get(url+'/api/sessions',timeout=5)
            assert sessions.status_code==200
            ids={s['session_id'] for s in sessions.json()}
            assert {session_id,report['browser']['session_id']} <= ids
            assert client.post(url+'/api/auth/logout',timeout=5).status_code==200
            assert client.get(url+'/api/sessions',timeout=5).status_code==401
            report.update(restart_preserves_session_and_recordings=True,logout_revokes_session=True,
                synthetic_sessions=[session_id,report['browser']['session_id']],passed=True)
            (state/'acceptance-report.json').write_text(json.dumps(report,indent=2))
            print(json.dumps(report,indent=2))
        finally:
            if process is not None and process.poll() is None:
                process.terminate(); process.wait(timeout=15)


if __name__=='__main__':
    main()
