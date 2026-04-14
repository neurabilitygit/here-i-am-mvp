from __future__ import annotations

import threading
import traceback
import uuid
from typing import Callable

from models.schemas import JobProgress


class JobManager:
    def __init__(self) -> None:
        self._jobs: dict[str, JobProgress] = {}
        self._lock = threading.Lock()

    def create(self, mode: str, message: str) -> JobProgress:
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
        return job

    def get(self, job_id: str) -> JobProgress | None:
        with self._lock:
            return self._jobs.get(job_id)

    def update(self, job_id: str, **kwargs) -> None:
        with self._lock:
            job = self._jobs[job_id]
            for key, value in kwargs.items():
                setattr(job, key, value)

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

        thread = threading.Thread(target=wrapped, daemon=True)
        thread.start()


job_manager = JobManager()
