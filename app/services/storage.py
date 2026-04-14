from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any

from slugify import slugify

from config import settings


def ensure_directories() -> None:
    for path in [
        Path(settings.sessions_dir),
        Path(settings.chroma_dir),
        Path(settings.logs_dir),
        Path(settings.tmp_dir),
    ]:
        path.mkdir(parents=True, exist_ok=True)


def create_session_dir(title: str | None = None) -> tuple[str, Path]:
    stamp = datetime.now().strftime('%Y-%m-%d_%H-%M-%S')
    suffix = slugify(title) if title else 'recording'
    session_id = f'{stamp}_{suffix}' if suffix else stamp
    session_path = Path(settings.sessions_dir) / session_id
    session_path.mkdir(parents=True, exist_ok=False)
    save_json(
        session_path / 'processing_state.json',
        {
            'session_id': session_id,
            'recorded': True,
            'transcribed': False,
            'analyzed': False,
            'embedded': False,
        },
    )
    return session_id, session_path


def save_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding='utf-8')


def load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding='utf-8'))


def update_processing_state(session_path: Path, **updates: Any) -> None:
    state_path = session_path / 'processing_state.json'
    state = load_json(state_path) if state_path.exists() else {}
    state.update(updates)
    save_json(state_path, state)


def session_paths(session_path: Path) -> dict[str, Path]:
    return {
        'audio': session_path / 'recording.flac',
        'transcript': session_path / 'transcript.md',
        'metadata': session_path / 'metadata.json',
        'chunks': session_path / 'chunks.jsonl',
        'state': session_path / 'processing_state.json',
    }


def list_session_dirs() -> list[Path]:
    sessions_root = Path(settings.sessions_dir)
    if not sessions_root.exists():
        return []
    return sorted([p for p in sessions_root.iterdir() if p.is_dir()])
