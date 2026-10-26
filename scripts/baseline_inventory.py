#!/usr/bin/env python3
"""Read-only source/audio inventory; never opens Chroma or reads credentials.

Print JSON to stdout. Audio samples are explicit paths, not automatically
selected private recordings. Run before each benchmark against the same files.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import platform
import subprocess
from pathlib import Path


def command(args):
    result = subprocess.run(args, capture_output=True, text=True, timeout=30)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed with exit {result.returncode}')
    return result.stdout.strip()


def sha256(path):
    digest = hashlib.sha256()
    with path.open('rb') as handle:
        while chunk := handle.read(1024 * 1024):
            digest.update(chunk)
    return digest.hexdigest()


def source_inventory(root):
    paths = command(['git', '-C', str(root), 'ls-files', '-z', '--', 'app', 'scripts', 'Dockerfile', 'docker-compose.yml', '*requirements*.txt']).split('\0')
    files = {}
    for value in paths:
        if not value or value.endswith(('.pyc', '.env')) or '/.env' in value:
            continue
        path = root / value
        if path.is_file():
            files[value] = sha256(path)
    return {
        'commit': command(['git', '-C', str(root), 'rev-parse', 'HEAD']),
        'dirty': bool(command(['git', '-C', str(root), 'status', '--porcelain', '--untracked-files=no'])),
        'files': files,
    }


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--candidate', type=Path, required=True)
    parser.add_argument('--deployed-source', type=Path, required=True)
    parser.add_argument('--sample', type=Path, action='append', default=[])
    parser.add_argument('--container', help='Optional running Docker container to compare with deployed source')
    args = parser.parse_args()
    candidate, deployed = source_inventory(args.candidate), source_inventory(args.deployed_source)
    paths = set(candidate['files']) | set(deployed['files'])
    changed = sorted(path for path in paths if candidate['files'].get(path) != deployed['files'].get(path))
    samples = []
    for path in args.sample:
        sample = {'path': str(path), 'bytes': path.stat().st_size, 'sha256': sha256(path)}
        try:
            probe = json.loads(command(['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)]))
            sample['duration_seconds'] = float(probe['format']['duration'])
        except (OSError, RuntimeError, KeyError, ValueError):
            sample['duration_seconds'] = None
        samples.append(sample)
    runtime = None
    if args.container:
        code = "import pathlib,hashlib,json; root=pathlib.Path('/app'); print(json.dumps({'app/'+str(p.relative_to(root)):hashlib.sha256(p.read_bytes()).hexdigest() for p in root.rglob('*') if p.is_file() and p.suffix in {'.py','.js','.css','.html'} and not p.name.startswith('._')}))"
        files = json.loads(command(['docker', 'exec', args.container, 'python', '-c', code]))
        scoped = {path: digest for path, digest in deployed['files'].items() if path.startswith('app/') and not path.startswith('app/app/') and Path(path).suffix in {'.py', '.js', '.css', '.html'}}
        runtime = {
            'image_id': command(['docker', 'inspect', args.container, '--format', '{{.Image}}']),
            'source_mismatches': sorted(path for path in set(files) | set(scoped) if files.get(path) != scoped.get(path)),
            'checked_files': len(files),
            'excluded_source_prefixes': ['app/app/ (dormant prototype)'],
        }
    print(json.dumps({'platform': platform.platform(), 'candidate': candidate, 'deployed_source': deployed, 'runtime': runtime, 'changed_files': changed, 'audio_samples': samples}, indent=2))


if __name__ == '__main__':
    main()
