from __future__ import annotations

import shutil
import time
from pathlib import Path

import requests


INBOX = Path("/Volumes/Personal/here-i-am/inbox")
PROCESSED = INBOX / "processed"
FAILED = INBOX / "failed"

APP_UPLOAD_URL = "http://localhost:8787/api/recordings/upload"
APP_TRANSCRIBE_URL = "http://localhost:8787/api/transcribe/start"

POLL_SECONDS = 5
AUDIO_EXTENSIONS = (".wav", ".m4a", ".mp3", ".flac")


def is_stable(file_path: Path, wait_seconds: int = 2) -> bool:
    try:
        size1 = file_path.stat().st_size
        time.sleep(wait_seconds)
        size2 = file_path.stat().st_size
        return size1 == size2 and size1 > 0
    except FileNotFoundError:
        return False


def upload_audio(file_path: Path) -> bool:
    try:
        with file_path.open("rb") as f:
            files = {"file": (file_path.name, f, "application/octet-stream")}
            data = {"title": file_path.stem}
            resp = requests.post(APP_UPLOAD_URL, files=files, data=data, timeout=300)
        resp.raise_for_status()
        print(f"[INBOX] Uploaded: {file_path.name}")
        return True
    except Exception as exc:
        print(f"[INBOX] Upload failed for {file_path.name}: {exc}")
        return False


def trigger_transcription() -> bool:
    try:
        resp = requests.post(APP_TRANSCRIBE_URL, timeout=60)
        resp.raise_for_status()
        data = resp.json()
        print(f"[INBOX] Transcription job started: {data.get('id', 'unknown')}")
        return True
    except Exception as exc:
        print(f"[INBOX] Failed to start transcription job: {exc}")
        return False


def move_to(src: Path, dst_dir: Path) -> None:
    dst_dir.mkdir(parents=True, exist_ok=True)
    target = dst_dir / src.name
    if target.exists():
        stem = src.stem
        suffix = src.suffix
        timestamp = int(time.time())
        target = dst_dir / f"{stem}_{timestamp}{suffix}"
    shutil.move(str(src), str(target))


def main() -> None:
    INBOX.mkdir(parents=True, exist_ok=True)
    PROCESSED.mkdir(parents=True, exist_ok=True)
    FAILED.mkdir(parents=True, exist_ok=True)

    print(f"[INBOX] Watching: {INBOX}")
    print(f"[INBOX] Uploading to: {APP_UPLOAD_URL}")
    print(f"[INBOX] Auto-transcribe endpoint: {APP_TRANSCRIBE_URL}")
    print(f"[INBOX] Accepted extensions: {', '.join(AUDIO_EXTENSIONS)}")

    while True:
        audio_files = sorted(
            p for p in INBOX.iterdir()
            if p.is_file() and p.suffix.lower() in AUDIO_EXTENSIONS
        )

        for audio_file in audio_files:
            if not is_stable(audio_file):
                continue

            success = upload_audio(audio_file)
            if success:
                move_to(audio_file, PROCESSED)
                trigger_transcription()
            else:
                move_to(audio_file, FAILED)

        time.sleep(POLL_SECONDS)


if __name__ == "__main__":
    main()
