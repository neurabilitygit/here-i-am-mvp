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
    if not args.confirm_empty_target:
        print(f"Verified {len(manifest.get('files', []))} files. Re-run with --confirm-empty-target to restore.")
        return 0
    if args.data_root.exists() and any(args.data_root.iterdir()):
        raise SystemExit('Restore target must be empty; existing data is never overwritten.')
    args.data_root.mkdir(parents=True, exist_ok=True)

    vector_export = args.backup / 'appdata' / 'chroma-export.jsonl'
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
        collection = client.get_or_create_collection(manifest.get('chroma_collection', 'here_i_am_chunks'))
        batch: list[dict] = []
        for line in vector_export.read_text(encoding='utf-8').splitlines():
            if line.strip():
                batch.append(json.loads(line))
            if len(batch) == 100:
                collection.add(
                    ids=[item['id'] for item in batch],
                    documents=[item['document'] for item in batch],
                    metadatas=[item['metadata'] for item in batch],
                    embeddings=[item['embedding'] for item in batch],
                )
                batch.clear()
        if batch:
            collection.add(
                ids=[item['id'] for item in batch],
                documents=[item['document'] for item in batch],
                metadatas=[item['metadata'] for item in batch],
                embeddings=[item['embedding'] for item in batch],
            )
    print(f'Restored verified backup into {args.data_root}')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
