from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
import json
import shutil
import uuid

from .config import SESSIONS_ROOT, STATE_ROOT, LOG_ROOT


@dataclass
class SessionPaths:
    session_id: str
    root: Path
    audio_input: Path
    audio_flac: Path
    transcript: Path
    metadata: Path
    processing_state: Path
    chunks_jsonl: Path


def utc_stamp() -> str:
    return datetime.now().strftime("%Y-%m-%d_%H-%M-%S")


def new_session_paths() -> SessionPaths:
    session_id = utc_stamp()
    root = SESSIONS_ROOT / session_id
    root.mkdir(parents=True, exist_ok=True)
    return SessionPaths(
        session_id=session_id,
        root=root,
        audio_input=root / "recording_input.bin",
        audio_flac=root / "recording.flac",
        transcript=root / "transcript.md",
        metadata=root / "metadata.json",
        processing_state=root / "processing_state.json",
        chunks_jsonl=root / "chunks.jsonl",
    )


def session_paths(session_id: str) -> SessionPaths:
    root = SESSIONS_ROOT / session_id
    return SessionPaths(
        session_id=session_id,
        root=root,
        audio_input=root / "recording_input.bin",
        audio_flac=root / "recording.flac",
        transcript=root / "transcript.md",
        metadata=root / "metadata.json",
        processing_state=root / "processing_state.json",
        chunks_jsonl=root / "chunks.jsonl",
    )


def list_sessions() -> list[Path]:
    if not SESSIONS_ROOT.exists():
        return []
    return sorted([p for p in SESSIONS_ROOT.iterdir() if p.is_dir()])


def write_json(path: Path, payload: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8")


def read_json(path: Path, default: dict | None = None) -> dict:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def update_processing_state(sp: SessionPaths, **kwargs) -> dict:
    state = read_json(sp.processing_state, default={
        "session_id": sp.session_id,
        "has_recording": sp.audio_flac.exists(),
        "has_transcript": sp.transcript.exists(),
        "has_metadata": sp.metadata.exists(),
        "has_chunks": sp.chunks_jsonl.exists(),
    })
    state.update(kwargs)
    state["has_recording"] = sp.audio_flac.exists()
    state["has_transcript"] = sp.transcript.exists()
    state["has_metadata"] = sp.metadata.exists()
    state["has_chunks"] = sp.chunks_jsonl.exists()
    write_json(sp.processing_state, state)
    return state


def write_job_state(job_name: str, payload: dict) -> None:
    write_json(STATE_ROOT / f"{job_name}.json", payload)


def read_job_state(job_name: str) -> dict:
    return read_json(STATE_ROOT / f"{job_name}.json", default={"status": "idle"})


def append_log(job_name: str, line: str) -> None:
    LOG_ROOT.mkdir(parents=True, exist_ok=True)
    with (LOG_ROOT / f"{job_name}.log").open("a", encoding="utf-8") as fh:
        fh.write(f"{datetime.now().isoformat()} {line}\n")


def create_temp_upload_file(original_name: str | None = None) -> Path:
    stem = uuid.uuid4().hex
    suffix = ""
    if original_name and "." in original_name:
        suffix = "." + original_name.rsplit(".", 1)[1].lower()
    path = STATE_ROOT.parent / "tmp" / f"{stem}{suffix}"
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def remove_path(path: Path) -> None:
    if path.is_dir():
        shutil.rmtree(path, ignore_errors=True)
    elif path.exists():
        path.unlink(missing_ok=True)
