import time

import pytest

from services.jobs import JobConflictError, JobManager


def test_jobs_are_persisted_and_duplicate_modes_are_blocked():
    manager = JobManager()
    job = manager.create('synthetic', 'queued')
    with pytest.raises(JobConflictError):
        manager.create('synthetic', 'duplicate')
    second_manager = JobManager()
    with pytest.raises(JobConflictError):
        second_manager.create('synthetic', 'cross-process duplicate')
    manager.run_in_thread(job.id, lambda: manager.update(job.id, status='done', completed=True))
    for _ in range(50):
        if manager.get(job.id).completed:
            break
        time.sleep(0.01)
    assert manager.get(job.id).status == 'done'
    assert (manager._root / f'{job.id}.json').exists()
