#!/usr/bin/env python3
"""Package/control a current-login-only managed native PILOT, never production.

Does not install login items, source .env, manage Docker/Ollama/Tailscale, move
data, or delete a release. Source is a verified read-only Git snapshot.
"""
import argparse
import hashlib
from io import BytesIO
import json
import os
from pathlib import Path
import plistlib
import stat
import subprocess
import tarfile

from native_pilot import REPO, PRODUCTION, check_initialized, check_port, inside, validate_pilot_origin

LABEL='org.hereiam.native-pilot'


def validate_bundle_destination(bundle,profile,root,state):
    bundle=bundle.resolve()
    for protected in (PRODUCTION.resolve(),Path('/data'),root,state,REPO):
        if inside(bundle,protected) or inside(protected,bundle):
            raise ValueError('Bundle must be separate from production, pilot data/state and source')
    if not profile.resolve().is_relative_to(bundle) or profile.is_symlink():
        raise ValueError('Profile must be inside its private bundle directory')
    return bundle


def checksum(path):
    h=hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda:handle.read(1024*1024),b''):
            h.update(chunk)
    return h.hexdigest()


def private_json(path,data):
    with path.open('x') as handle:
        os.chmod(path,0o600)
        json.dump(data,handle,indent=2); handle.flush(); os.fsync(handle.fileno())


def package_release(destination):
    if subprocess.check_output(['git','-C',str(REPO),'status','--porcelain'],text=True).strip():
        raise ValueError('Commit/review the working tree before packaging; dirty source is refused')
    commit=subprocess.check_output(['git','-C',str(REPO),'rev-parse','HEAD'],text=True).strip()
    release=destination/'releases'/commit
    if release.exists():
        verify_release(release)
        return release
    archive=subprocess.check_output(['git','-C',str(REPO),'archive','--format=tar',commit])
    with tarfile.open(fileobj=BytesIO(archive)) as data:
        for item in data.getmembers():
            path=Path(item.name)
            if path.is_absolute() or '..' in path.parts or not (item.isfile() or item.isdir()):
                raise ValueError('Unsupported or escaping source archive entry')
        release.mkdir(parents=True,mode=0o700)
        data.extractall(release,filter='data')
    files={str(p.relative_to(release)):checksum(p) for p in release.rglob('*') if p.is_file()}
    private_json(release/'release-manifest.json',{'commit':commit,'files':files})
    for path in release.rglob('*'):
        path.chmod(0o555 if path.is_dir() or path.stat().st_mode & 0o111 else 0o444)
    release.chmod(0o555)
    return release


def verify_release(release):
    if release.is_symlink():
        raise ValueError('Release cannot be a symlink')
    manifest=json.loads((release/'release-manifest.json').read_text())
    listed=manifest.get('files',{})
    paths=list(release.rglob('*'))
    if any(path.is_symlink() for path in paths):
        raise ValueError('Release cannot contain symlinks')
    actual={str(p.relative_to(release)) for p in paths if p.is_file() and p!=release/'release-manifest.json'}
    if not listed or set(listed)!=actual:
        raise ValueError('Release file inventory differs from its manifest')
    for name,digest in listed.items():
        path=release/name
        if path.is_symlink() or not path.resolve().is_relative_to(release.resolve()) or checksum(path)!=digest:
            raise ValueError('Release integrity check failed')
    return manifest['commit']


def build_plist(profile):
    source=Path(profile['source_root']); state=Path(profile['state_dir'])
    args=[profile['backend_python'],str(source/'scripts/run_native_phone_pilot.py')]
    for flag,key in [('--data-root','data_root'),('--state-dir','state_dir'),('--voice-python','voice_python'),
                     ('--model-path','model_path'),('--pilot-origin','pilot_origin')]:
        args.extend([flag,profile[key]])
    return {'Label':LABEL,'ProgramArguments':args,'WorkingDirectory':str(source),
            'RunAtLoad':True,'KeepAlive':{'SuccessfulExit':False},'ThrottleInterval':30,
            'ExitTimeOut':45,'AbandonProcessGroup':False,'ProcessType':'Background','Umask':0o077,
            'EnvironmentVariables':{'PATH':'/opt/homebrew/bin:/usr/bin:/bin:/usr/sbin:/sbin','PYTHONDONTWRITEBYTECODE':'1'},
            'StandardOutPath':str(state/'managed-supervisor.log'),'StandardErrorPath':str(state/'managed-supervisor-error.log')}


def validate_profile(profile):
    if profile.get('schema')!=1 or profile.get('label')!=LABEL or profile.get('login_autostart') is not False:
        raise ValueError('Only the explicit current-login pilot profile is supported')
    root,state=check_initialized(Path(profile['data_root']),Path(profile['state_dir']))
    validate_pilot_origin(profile['pilot_origin'])
    source=Path(profile['source_root'])
    if verify_release(source)!=profile['source_commit']:
        raise ValueError('Release commit mismatch')
    python=Path(profile['backend_python'])
    if not python.is_absolute() or not python.is_file() or str(python).startswith(('/tmp/','/private/tmp/')):
        raise ValueError('A durable, separate native runtime is required')
    # Import only the launcher verifier, with no application/config imports.
    env={'PATH':'/opt/homebrew/bin:/usr/bin:/bin','PYTHONPATH':str(source/'scripts'),'PYTHONDONTWRITEBYTECODE':'1'}
    subprocess.run([str(python),'-c','from native_pilot import check_runtime; check_runtime()'],env=env,cwd=state,check=True,timeout=30)
    if not Path(profile['voice_python']).is_file() or not (Path(profile['model_path'])/'config.json').is_file():
        raise ValueError('Existing local voice runtime/model is unavailable')
    return root,state


def read_profile(path):
    if path.is_symlink() or stat.S_IMODE(path.stat().st_mode)!=0o600:
        raise ValueError('Service profile must be a private regular file')
    profile=json.loads(path.read_text())
    return profile


def service_target():
    return f'gui/{os.getuid()}/{LABEL}'


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('command',choices=['prepare','check','start','stop','status'])
    p.add_argument('--profile',type=Path,required=True)
    for name in ('bundle-root','data-root','state-dir','backend-python','voice-python','model-path'):
        p.add_argument('--'+name,type=Path)
    p.add_argument('--pilot-origin')
    args=p.parse_args()
    if args.command=='prepare':
        if not all([args.bundle_root,args.data_root,args.state_dir,args.backend_python,args.voice_python,args.model_path,args.pilot_origin]):
            p.error('prepare requires all paths and the explicit private pilot origin')
        if args.profile.exists():
            raise ValueError('Profile exists; prepare a new version instead of overwriting')
        root,state=check_initialized(args.data_root,args.state_dir)
        validate_pilot_origin(args.pilot_origin)
        bundle=validate_bundle_destination(args.bundle_root,args.profile,root,state)
        if args.profile.with_suffix('.plist').exists():
            raise ValueError('Service definition already exists; nothing overwritten')
        bundle.mkdir(parents=True,exist_ok=True); bundle.chmod(0o700)
        release=package_release(bundle)
        profile={'schema':1,'label':LABEL,'source_root':str(release),'source_commit':verify_release(release),
                 'data_root':str(root),'state_dir':str(state),'backend_python':str(args.backend_python.absolute()),
                 'voice_python':str(args.voice_python.absolute()),'model_path':str(args.model_path.resolve()),
                 'pilot_origin':args.pilot_origin,'login_autostart':False}
        validate_profile(profile)
        args.profile.parent.mkdir(parents=True,exist_ok=True)
        private_json(args.profile,profile)
        plist=args.profile.with_suffix('.plist')
        with plist.open('xb') as handle:
            os.chmod(plist,0o600); plistlib.dump(build_plist(profile),handle)
        print(json.dumps({'prepared':True,'commit':profile['source_commit'],'login_autostart':False}))
        return
    profile=read_profile(args.profile)
    if args.command in {'check','start'}:
        validate_profile(profile)
    if args.command=='start':
        for port in (8792,8793): check_port(port)
        plist=args.profile.with_suffix('.plist')
        if plist.is_symlink() or plistlib.loads(plist.read_bytes())!=build_plist(profile):
            raise ValueError('Service definition differs from the validated profile')
        subprocess.run(['/bin/launchctl','bootstrap',f'gui/{os.getuid()}',str(plist)],check=True)
        print('Managed pilot requested for this login only; check readiness before use.')
    elif args.command=='stop':
        # Fixed label only, never arbitrary PIDs or production services. Remains
        # usable even when the data disk/source/runtime is unavailable.
        subprocess.run(['/bin/launchctl','bootout',service_target()],check=True)
        print('Managed pilot stopped; data, VPN routes, and releases retained.')
    elif args.command=='status':
        result=subprocess.run(['/bin/launchctl','print',service_target()],capture_output=True,text=True)
        print(result.stdout if result.returncode==0 else 'Managed pilot is not loaded.')
    else:
        print('Profile, source inventory, data isolation and pinned runtime verified.')


if __name__=='__main__':
    main()
