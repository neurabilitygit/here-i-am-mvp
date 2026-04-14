from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from .config import get_settings


@dataclass(frozen=True)
class AppPaths:
    root: Path
    sessions: Path
    chroma: Path
    logs: Path
    tmp: Path
    jobs: Path
    status: Path
    state: Path
    ollama: Path


def ensure_directories() -> AppPaths:
    settings = get_settings()
    root = settings.data_root
    sessions = root / 'library' / 'sessions'
    chroma = root / 'appdata' / 'chroma'
    logs = root / 'appdata' / 'logs'
    tmp = root / 'appdata' / 'tmp'
    jobs = root / 'appdata' / 'jobs'
    status = root / 'appdata' / 'status'
    state = root / 'appdata' / 'state'
    ollama = root / 'appdata' / 'ollama'

    for path in [sessions, chroma, logs, tmp, jobs, status, state, ollama]:
        path.mkdir(parents=True, exist_ok=True)

    return AppPaths(
        root=root,
        sessions=sessions,
        chroma=chroma,
        logs=logs,
        tmp=tmp,
        jobs=jobs,
        status=status,
        state=state,
        ollama=ollama,
    )
