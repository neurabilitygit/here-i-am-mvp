"""Admission control for this application's heavyweight local inference.

The lock is shared by threads and worker processes in one container. It does
not coordinate other apps, separate containers, or direct native CLI requests.
Embeddings are deliberately not heavyweight: cloud Talk can still retrieve
memories while local voice is working. No prompts or private facts are stored.
"""
from __future__ import annotations

import fcntl
import inspect
import threading
from contextlib import contextmanager
from functools import wraps
from pathlib import Path

import requests

from config import settings


class LocalWorkloadBusy(RuntimeError):
    pass


class LocalWorkloads:
    def __init__(self):
        self._lock = threading.RLock()
        self._owner = threading.local()
        self._active = ''

    @contextmanager
    def claim(self, kind: str):
        if not self._lock.acquire(blocking=False):
            raise LocalWorkloadBusy('This Mac is already preparing a local answer, voice, or memories. Wait for it to finish, or cancel the active voice before trying again.')
        handle = None
        nested = getattr(self._owner, 'depth', 0) > 0
        try:
            if not nested:
                path = Path(settings.local_workload_lock_path)
                path.parent.mkdir(parents=True, exist_ok=True)
                handle = path.open('a+')
                try:
                    fcntl.flock(handle.fileno(), fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    raise LocalWorkloadBusy('Another application worker is using local AI. Try again when it finishes.') from exc
                self._active = kind
            self._owner.depth = getattr(self._owner, 'depth', 0) + 1
            try:
                yield
            finally:
                self._owner.depth -= 1
                if not nested:
                    self._active = ''
        finally:
            if handle is not None:
                handle.close()  # closing also releases flock, including failures
            self._lock.release()


local_workloads = LocalWorkloads()


def exclusive_local_workload(kind: str):
    """Keep ownership through a generator's iteration, not just its creation."""
    def decorate(function):
        if inspect.isgeneratorfunction(function):
            @wraps(function)
            def generate(*args, **kwargs):
                with local_workloads.claim(kind):
                    yield from function(*args, **kwargs)
            return generate
        @wraps(function)
        def run(*args, **kwargs):
            with local_workloads.claim(kind):
                return function(*args, **kwargs)
        return run
    return decorate


def release_idle_voice() -> None:
    """Release native MLX weights, never voice identity or prepared audio.

An active/orphaned native request must finish before heavy Ollama/ASR work.
Connection refusal permits operation when the optional bridge is stopped;
timeouts or an incompatible running bridge fail closed.
"""
    if not settings.local_bridge_token:
        return
    base = settings.voice_bridge_url.rstrip('/')
    try:
        response = requests.get(f'{base}/health', timeout=(2, 2))
        response.raise_for_status()
        status = response.json()
    except requests.Timeout as exc:
        raise LocalWorkloadBusy('The local voice status could not be checked. Try again shortly.') from exc
    except requests.ConnectionError:
        return
    except (requests.RequestException, ValueError) as exc:
        raise LocalWorkloadBusy('The local voice status could not be checked. Try again shortly.') from exc
    if status.get('busy'):
        raise LocalWorkloadBusy('Your local voice is still preparing audio. Wait for it to finish, or cancel it before asking Local Gemma.')
    if status.get('model_loaded'):
        try:
            released = requests.post(f'{base}/model/unload', headers={'X-Here-I-Am-Local': settings.local_bridge_token}, timeout=(2, 10))
            released.raise_for_status()
        except requests.RequestException as exc:
            raise LocalWorkloadBusy('The local voice could not release memory. Check that the app and voice bridge are on the same version.') from exc
