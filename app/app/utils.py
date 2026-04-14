from __future__ import annotations

import json
import re
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

from .config import get_settings


def slugify(value: str) -> str:
    value = value.strip().lower()
    value = re.sub(r'[^a-z0-9]+', '-', value)
    return value.strip('-') or 'session'


def now_session_stamp() -> str:
    settings = get_settings()
    return datetime.now(ZoneInfo(settings.session_timezone)).strftime('%Y-%m-%d_%H-%M-%S')


def write_json(path: Path, payload: dict) -> None:
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding='utf-8')


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding='utf-8'))


def safe_filename(path_str: str) -> str:
    return Path(path_str).name
