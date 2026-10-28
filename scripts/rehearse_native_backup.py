#!/usr/bin/env python3
"""Non-destructive backup/restore rehearsal on a stopped, marked pilot only.

Production is never loaded. Restore only into a new folder; retain every copy.
No inference, transcription, vector deletion, or VPN change is performed.
"""
import argparse
import hashlib
import json
import os
from pathlib import Path
import secrets
import shutil
import subprocess
import sys
import time

import requests

from native_pilot import REPO, PRODUCTION, check_initialized, check_port, check_runtime, initialize, inside, settings_for
from restore_backup import digest


def new_destination(path: Path, source: Path, state: Path) -> Path:
    path = path.resolve()
    if path.exists():
        raise ValueError('Rehearsal destinations must be new; nothing is overwritten')
    for protected in (PRODUCTION.resolve(), Path('/data'), source, state):
        if inside(path, protected) or inside(protected, path):
            raise ValueError('Rehearsal destination overlaps protected data')
    return path


def vector_snapshot(client):
    result = {}
    for collection in client.list_collections():
        collection = client.get_collection(collection.name)
        rows = collection.get(include=['documents','metadatas','embeddings'])
        records = {key:{'document':rows['documents'][i], 'metadata':rows['metadatas'][i],
                        'embedding':rows['embeddings'][i].tolist()} for i,key in enumerate(rows['ids'])}
        result[collection.name] = {'metadata':collection.metadata,'records':records}
    return result


def fingerprint(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':')).encode()).hexdigest()


def session_count(root: Path) -> int:
    return sum(1 for path in (root/'library/sessions').iterdir()
               if not path.name.startswith('._') and path.is_dir())


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('--data-root',type=Path,required=True)
    p.add_argument('--state-dir',type=Path,required=True)
    p.add_argument('--restore-root',type=Path,required=True)
    p.add_argument('--report-dir',type=Path,required=True)
    p.add_argument('--recording-id',required=True)
    p.add_argument('--confirm-isolated-rehearsal',action='store_true',required=True)
    args=p.parse_args()
    root,state=check_initialized(args.data_root,args.state_dir)
    check_runtime()
    # The operator stops only the known pilot supervisor before this program.
    for port in (8792,8793,8794):
        check_port(port)
    restored=new_destination(args.restore_root,root,state)
    report_dir=new_destination(args.report_dir,root,state)
    if inside(restored,report_dir) or inside(report_dir,restored):
        raise ValueError('Backup evidence and restore directories must be separate')
    if not args.recording_id or Path(args.recording_id).name != args.recording_id:
        raise ValueError('Invalid recording ID')
    recording=root/'library/sessions'/args.recording_id
    original_recording=json.loads((recording/'processing_state.json').read_text())
    if original_recording.get('upload_status')!='ready':
        raise ValueError('The selected recording has not passed upload validation')
    if digest(recording/'recording.source')!=original_recording['source_sha256']:
        raise ValueError('Recording source checksum mismatch')
    report_dir.mkdir(parents=True,mode=0o700)
    os.chmod(report_dir,0o700)
    restore_state=report_dir/'restored-private-state'
    os.environ.clear()
    os.environ.update(PATH='/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin',
                      ANONYMIZED_TELEMETRY='False',OTEL_SDK_DISABLED='true',PYTHONDONTWRITEBYTECODE='1')
    os.chdir(report_dir)
    sys.path.insert(0,str(REPO/'app'))
    import config
    values=settings_for(root,state,8794)
    values['backup_root']=str(report_dir/'backups')
    config.settings=config.Settings(_env_file=None,**values)
    from services.library import create_structured_backup
    import chromadb
    from chromadb.config import Settings
    source_client=chromadb.PersistentClient(path=str(root/'appdata/chroma'),settings=Settings(anonymized_telemetry=False))
    before_vectors=vector_snapshot(source_client)
    report={'production_touched':False,'phase':'backup',
            'recording_id':args.recording_id,'recording_seconds':original_recording['duration_seconds']}
    child=None
    def save_report():
        (report_dir/'rehearsal.json').write_text(json.dumps(report,indent=2))
    try:
        started=time.perf_counter()
        result=create_structured_backup()
        backup=report_dir/'backups'/result['backup_id']
        manifest=json.loads((backup/'manifest.json').read_text())
        report.update(backup=result,backup_seconds=time.perf_counter()-started,backup_path=str(backup),phase='restore')
        save_report()
        print(json.dumps({'backup_complete':True,'files':result['files'],'seconds':report['backup_seconds']}),flush=True)
        # Runtime credentials are outside DATA_ROOT and need an independent,
        # private recovery supplement. Never log their contents.
        runtime=report_dir/'private-runtime-recovery'; runtime.mkdir(mode=0o700)
        runtime_records={}
        for name in ('passphrase.json','auth_tokens.json','voice-bridge-token.json','local-clone-test.wav'):
            source=state/name
            if source.is_file():
                shutil.copy2(source,runtime/name); os.chmod(runtime/name,0o600)
                if digest(source)!=digest(runtime/name):
                    raise RuntimeError('Private runtime recovery copy mismatch')
                runtime_records[name]={'bytes':source.stat().st_size,'sha256':digest(source)}
        (runtime/'manifest.json').write_text(json.dumps(runtime_records,indent=2))
        report['private_runtime_files_verified']=len(runtime_records)
        restore_command=[sys.executable,str(REPO/'scripts/restore_backup.py'),str(backup),str(restored),'--confirm-empty-target']
        started=time.perf_counter()
        completed=subprocess.run(restore_command,capture_output=True,text=True,timeout=180)
        (report_dir/'restore.log').write_text(completed.stdout+completed.stderr)
        if completed.returncode:
            raise RuntimeError('Restore failed; inspect private restore.log')
        report['restore_seconds']=time.perf_counter()-started
        report['phase']='verify'
        verified=0
        for item in manifest['files']:
            if item['path']=='appdata/chroma-export.jsonl':
                continue
            target=restored/item['path']
            if target.stat().st_size!=item['bytes'] or digest(target)!=item['sha256']:
                raise RuntimeError('Restored file verification failed')
            if digest(root/item['path'])!=item['sha256']:
                raise RuntimeError('Source changed during the stopped-pilot rehearsal')
            verified+=1
        restored_client=chromadb.PersistentClient(path=str(restored/'appdata/chroma'),settings=Settings(anonymized_telemetry=False))
        restored_vectors=vector_snapshot(restored_client)
        if before_vectors!=restored_vectors or before_vectors!=vector_snapshot(source_client):
            raise RuntimeError('Vector identities or values changed')
        probes=0
        for name,data in before_vectors.items():
            vectors=[r['embedding'] for r in data['records'].values()][:8]
            if vectors:
                first=source_client.get_collection(name).query(query_embeddings=vectors,n_results=min(6,len(data['records'])),include=['distances'])
                second=restored_client.get_collection(name).query(query_embeddings=vectors,n_results=min(6,len(data['records'])),include=['distances'])
                if first['ids']!=second['ids'] or first['distances']!=second['distances']:
                    raise RuntimeError('Restored retrieval results differ')
                probes+=len(vectors)
        report.update(restored_files_verified=verified,all_source_files_unchanged=True,
                      vectors_verified=sum(len(c['records']) for c in before_vectors.values()),
                      vector_fields_sha256=fingerprint(before_vectors),vector_query_probes=probes,
                      query_results_identical=True,
                      restored_sessions=session_count(restored))
        # Restore must refuse an occupied target, with no overwrite or deletion.
        refusal=subprocess.run(restore_command,capture_output=True,text=True,timeout=60)
        if refusal.returncode==0 or 'must be empty' not in refusal.stderr:
            raise RuntimeError('Occupied-target safety check failed')
        report['occupied_target_refused']=True
        password=secrets.token_urlsafe(32)
        initialize(restored,restore_state,password)
        report['phase']='restored_app'
        save_report()
        command=[sys.executable,str(REPO/'scripts/native_pilot.py'),'run','--data-root',str(restored),
                 '--state-dir',str(restore_state),'--port','8794']
        client=requests.Session(); client.trust_env=False
        url='http://127.0.0.1:8794'
        with (report_dir/'restored-app.log').open('w') as log:
            child=subprocess.Popen(command,stdin=subprocess.DEVNULL,stdout=log,stderr=log)
            for _ in range(150):
                if child.poll() is not None:
                    raise RuntimeError('Restored app failed to start')
                try:
                    if client.get(url+'/api/health',timeout=.5).ok:
                        break
                except requests.RequestException:
                    pass
                time.sleep(.1)
            else:
                raise RuntimeError('Restored app startup timed out')
            assert client.get(url+'/api/sessions',timeout=5).status_code==401
            assert client.post(url+'/api/auth/login',json={'passphrase':password},timeout=5).status_code==200
            sessions=client.get(url+'/api/sessions',timeout=5).json()
            assert len(sessions)==report['restored_sessions']
            audio=client.get(url+'/api/sessions/'+args.recording_id+'/audio',timeout=10)
            assert audio.status_code==200 and hashlib.sha256(audio.content).hexdigest()==digest(recording/'recording.flac')
            browser=subprocess.run(['node',str(REPO/'scripts/check_restored_library_browser.cjs')],
                input=json.dumps({'url':url,'passphrase':password,'recordingId':args.recording_id,
                                 'count':len(sessions),'seconds':original_recording['duration_seconds'],
                                 'audioSha256':digest(recording/'recording.flac')}),
                capture_output=True,text=True,timeout=60)
            if browser.returncode:
                raise RuntimeError('Restored browser failed: '+browser.stderr[-1500:])
            report.update(authenticated_recording_bytes_identical=True,browser=json.loads(browser.stdout),
                          phase='complete',passed=True)
            save_report()
            print(json.dumps(report,indent=2),flush=True)
    except BaseException:
        report['passed']=False; save_report()
        raise
    finally:
        if child is not None and child.poll() is None:
            child.terminate()
            try: child.wait(timeout=15)
            except subprocess.TimeoutExpired:
                child.kill(); child.wait(timeout=5)


if __name__=='__main__':
    main()
