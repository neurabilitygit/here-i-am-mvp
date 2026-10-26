#!/usr/bin/env python3
"""Verify and restore a Here I Am backup into an empty data root."""
from __future__ import annotations

import argparse
import hashlib
import json
import shutil
from pathlib import Path


def digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open('rb') as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b''):
            value.update(chunk)
    return value.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('backup', type=Path)
    parser.add_argument('data_root', type=Path)
    parser.add_argument('--confirm-empty-target', action='store_true')
    args = parser.parse_args()

    manifest_path = args.backup / 'manifest.json'
    manifest = json.loads(manifest_path.read_text(encoding='utf-8'))
    for record in manifest.get('files', []):
        source = args.backup / record['path']
        if not source.is_file() or source.stat().st_size != record['bytes'] or digest(source) != record['sha256']:
            raise SystemExit(f"Backup verification failed: {record['path']}")
    vector_export = args.backup / 'appdata' / 'chroma-export.jsonl'
    descriptors = manifest.get('chroma_collections')
    if descriptors is None:
        descriptors = [{'name': manifest.get('chroma_collection', 'here_i_am_chunks'), 'metadata': None}]
    by_name = {item['name']: item for item in descriptors}
    if len(by_name) != len(descriptors):
        raise SystemExit('Backup contains duplicate collection names')
    counts = dict.fromkeys(by_name, 0)
    seen_ids = set()
    if vector_export.exists():
        with vector_export.open(encoding='utf-8') as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                name = item.get('collection', manifest.get('chroma_collection', 'here_i_am_chunks'))
                key = (name, item['id'])
                if name not in by_name or key in seen_ids or not item.get('embedding'):
                    raise SystemExit('Invalid or duplicate vector in backup')
                seen_ids.add(key)
                counts[name] += 1
    for name, descriptor in by_name.items():
        if 'count' in descriptor and descriptor['count'] != counts[name]:
            raise SystemExit(f'Backup collection count mismatch: {name}')
    if not args.confirm_empty_target:
        print(f"Verified {len(manifest.get('files', []))} files. Re-run with --confirm-empty-target to restore.")
        return 0
    if args.data_root.exists() and any(args.data_root.iterdir()):
        raise SystemExit('Restore target must be empty; existing data is never overwritten.')
    args.data_root.mkdir(parents=True, exist_ok=True)

    for record in manifest.get('files', []):
        source = args.backup / record['path']
        if source == vector_export:
            continue
        destination = args.data_root / record['path']
        destination.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, destination)

    if vector_export.exists():
        import chromadb

        client = chromadb.PersistentClient(path=str(args.data_root / 'appdata' / 'chroma'))
        collections = {name: client.get_or_create_collection(name, metadata=descriptor.get('metadata')) for name, descriptor in by_name.items()}
        batches: dict[str, list[dict]] = {name: [] for name in by_name}

        def flush(name):
            batch = batches[name]
            if not batch:
                return
            collections[name].add(
                ids=[item['id'] for item in batch],
                documents=[item['document'] for item in batch] if any(item['document'] is not None for item in batch) else None,
                metadatas=[item['metadata'] for item in batch] if any(item['metadata'] is not None for item in batch) else None,
                embeddings=[item['embedding'] for item in batch],
            )
            batch.clear()

        with vector_export.open(encoding='utf-8') as handle:
            for line in handle:
                if not line.strip():
                    continue
                item = json.loads(line)
                name = item.get('collection', manifest.get('chroma_collection', 'here_i_am_chunks'))
                batches[name].append(item)
                if len(batches[name]) == 100:
                    flush(name)
        for name in collections:
            flush(name)
            if collections[name].count() != counts[name]:
                raise SystemExit(f'Restored collection count mismatch: {name}')
    print(f'Restored verified backup into {args.data_root}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
