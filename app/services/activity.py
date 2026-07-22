from __future__ import annotations

import re
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from config import settings
from models.schemas import ClientActivityEvent
from services.jsonl_store import append_jsonl, recent_jsonl


_WRITE_LOCK = threading.Lock()
_SAFE_KEY = re.compile(r'^[a-z][a-z0-9_]{0,63}$')
_SENSITIVE_KEY_PARTS = ('answer_text', 'question_text', 'prompt', 'transcript', 'recording', 'content')


def _safe_details(details: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key, value in list(details.items())[:30]:
        if not _SAFE_KEY.fullmatch(key) or any(part in key for part in _SENSITIVE_KEY_PARTS):
            continue
        if value is None or isinstance(value, (bool, int, float)):
            safe[key] = value
        elif isinstance(value, str):
            safe[key] = value[:120]
    return safe


def record_activity(payload: ClientActivityEvent, *, request_id: str = '') -> dict[str, Any]:
    path = Path(settings.activity_event_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    event = {
        'received_at': datetime.now(timezone.utc).isoformat(),
        'occurred_at': payload.occurred_at.isoformat(),
        'request_id': request_id,
        'page_id': payload.page_id,
        'sequence': payload.sequence,
        'event': payload.event,
        'scene': payload.scene,
        'details': _safe_details(payload.details),
    }
    with _WRITE_LOCK:
        append_jsonl(path, event)
    return event


def recent_activity(limit: int = 100) -> list[dict[str, Any]]:
    path = Path(settings.activity_event_path)
    if not path.exists():
        return []
    with _WRITE_LOCK:
        return recent_jsonl(path, limit)
