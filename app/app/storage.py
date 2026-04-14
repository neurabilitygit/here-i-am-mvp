from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

from .paths import ensure_directories
from .utils import now_session_stamp, slugify


def create_session_folder(title_hint: str | None = None) -> tuple[str, Path]:
    paths = ensure_directories()
    stamp = now_session_stamp()
    suffix = f'_{slugify(title_hint)}' if title_hint else ''
    session_id = f'{stamp}{suffix}'
    session_dir = paths.sessions / session_id
    session_dir.mkdir(parents=True, exist_ok=False)
    return session_id, session_dir


def convert_audio_to_flac(source_path: Path, target_path: Path) -> None:
    target_path.parent.mkdir(parents=True, exist_ok=True)
    subprocess.run(
        ['ffmpeg', '-y', '-i', str(source_path), '-c:a', 'flac', str(target_path)],
        check=True,
        capture_output=True,
    )


def save_upload_temp(upload_bytes: bytes, filename: str) -> Path:
    paths = ensure_directories()
    tmp_path = paths.tmp / filename
    tmp_path.write_bytes(upload_bytes)
    return tmp_path


def remove_file(path: Path) -> None:
    if path.exists():
        if path.is_file():
            path.unlink()
        else:
            shutil.rmtree(path)
