from __future__ import annotations

import json
import threading
import traceback
import uuid
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from config import settings
from models.schemas import JobProgress
from services.storage import atomic_write_text


class JobConflictError(RuntimeError):
    pass


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobProgress] = {}
        self._lock = threading.Lock()
        self._active_modes: set[str] = set()
        self._executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix='here-i-am-job')
        self._root = Path(settings.jobs_dir)
        self._root.mkdir(parents=True, exist_ok=True)
        self._load_existing()

    def _load_existing(self) -> None:
        for path in sorted(self._root.glob('*.json')):
            try:
                job = JobProgress.model_validate_json(path.read_text(encoding='utf-8'))
            except Exception:
                continue
            if not job.completed and job.status in {'queued', 'running'}:
                job.status = 'interrupted'
                job.message = 'Interrupted by application restart; safe to retry'
                job.completed = True
                job.updated_at = datetime.now(timezone.utc)
                self._save(job)
            self._jobs[job.id] = job

    def _save(self, job: JobProgress) -> None:
        atomic_write_text(self._root / f'{job.id}.json', job.model_dump_json(indent=2))

    def create(self, mode: str, message: str) -> JobProgress:
        with self._lock:
            if mode in self._active_modes:
                raise JobConflictError(f'A {mode} job is already active')
        job = JobProgress(
            id=str(uuid.uuid4()),
            mode=mode,
            status='queued',
            message=message,
            processed=0,
            total=0,
            completed=False,
            result={},
        )
        with self._lock:
            self._jobs[job.id] = job
            self._active_modes.add(mode)
            self._save(job)
        return job

    def get(self, job_id: str) -> JobProgress | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 100) -> list[JobProgress]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda job: job.created_at, reverse=True)[:limit]

    def is_active(self, mode: str | None = None) -> bool:
        with self._lock:
            return bool(self._active_modes) if mode is None else mode in self._active_modes

    def active_job(self, mode: str) -> JobProgress | None:
        with self._lock:
            active = [job for job in self._jobs.values() if job.mode == mode and not job.completed]
            return max(active, key=lambda job: job.created_at) if active else None

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in kwargs.items():
                setattr(job, key, value)
            job.updated_at = datetime.now(timezone.utc)
            if job.completed:
                self._active_modes.discard(job.mode)
            self._save(job)

    def run_in_thread(self, job_id: str, target: Callable[[], None]) -> None:
        def wrapped() -> None:
            try:
                target()
            except Exception as exc:
                traceback.print_exc()
                self.update(
                    job_id,
                    status='error',
                    message=f'Background job failed: {exc}',
                    completed=True,
                    result={'error': str(exc)},
                )

        self._executor.submit(wrapped)


job_manager = JobManager()
