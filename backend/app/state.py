from __future__ import annotations

import threading
from typing import Callable


class SingleJobRunner:
    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._threads: dict[str, threading.Thread] = {}

    def is_running(self, name: str) -> bool:
        with self._lock:
            thread = self._threads.get(name)
            return bool(thread and thread.is_alive())

    def start(self, name: str, target: Callable[[], None]) -> bool:
        with self._lock:
            existing = self._threads.get(name)
            if existing and existing.is_alive():
                return False
            thread = threading.Thread(target=target, name=name, daemon=True)
            self._threads[name] = thread
            thread.start()
            return True


runner = SingleJobRunner()
