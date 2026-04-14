from __future__ import annotations

import uuid
from pathlib import Path

from .paths import ensure_directories
from .utils import read_json, write_json


def enqueue_job(job_type: str, session_id: str) -> str:
    paths = ensure_directories()
    job_id = str(uuid.uuid4())
    job_path = paths.jobs / f'{job_type}_{job_id}.json'
    write_json(job_path, {'job_id': job_id, 'job_type': job_type, 'session_id': session_id, 'state': 'queued'})
    return job_id


def get_processing_state(session_path: Path) -> dict:
    state_path = session_path / 'processing_state.json'
    state = read_json(
        state_path,
        default={
            'transcribed': False,
            'analyzed': False,
            'recording_saved': False,
        },
    )
    return state


def save_processing_state(session_path: Path, **kwargs) -> dict:
    state = get_processing_state(session_path)
    state.update(kwargs)
    write_json(session_path / 'processing_state.json', state)
    return state
