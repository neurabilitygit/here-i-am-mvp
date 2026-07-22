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


def test_background_job_errors_do_not_expose_internal_details():
    manager = JobManager()
    job = manager.create('failure-test', 'queued')

    def fail():
        raise RuntimeError('/private/path and provider response details')

    manager.run_in_thread(job.id, fail)
    for _ in range(50):
        if manager.get(job.id).completed:
            break
        time.sleep(0.01)
    failed = manager.get(job.id)
    assert failed.status == 'error'
    assert '/private/path' not in failed.message
    assert failed.result['error_code'] == 'background_job_failed'
