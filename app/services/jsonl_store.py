from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings


def append_jsonl(path: Path, record: dict[str, Any]) -> None:
    """Append one durable JSON record and preserve full rotated history."""
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists() and path.stat().st_size >= settings.jsonl_rotate_bytes:
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        archived = path.with_name(f'{path.stem}.{stamp}{path.suffix}')
        os.replace(path, archived)
    descriptor = os.open(path, os.O_APPEND | os.O_CREAT | os.O_WRONLY, 0o600)
    with os.fdopen(descriptor, 'a', encoding='utf-8') as handle:
        handle.write(json.dumps(record, ensure_ascii=False, separators=(',', ':')) + '\n')
        handle.flush()
        os.fsync(handle.fileno())


def recent_jsonl(path: Path, limit: int) -> list[dict[str, Any]]:
    candidates = sorted(path.parent.glob(f'{path.stem}.*{path.suffix}')) + [path]
    lines: list[str] = []
    for candidate in reversed(candidates):
        if not candidate.exists():
            continue
        candidate_lines = candidate.read_text(encoding='utf-8').splitlines()
        lines = candidate_lines[-limit:] + lines
        if len(lines) >= limit:
            break
    records: list[dict[str, Any]] = []
    for line in lines[-limit:]:
        try:
            value = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(value, dict):
            records.append(value)
    return records
