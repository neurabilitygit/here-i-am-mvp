from __future__ import annotations

import json
import os
import re
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import chromadb
import httpx
from faster_whisper import WhisperModel

HERE_I_AM_ROOT = Path(os.getenv("HERE_I_AM_ROOT", "/data"))
LIBRARY_ROOT = Path(os.getenv("LIBRARY_ROOT", str(HERE_I_AM_ROOT / "library")))
APPDATA_ROOT = Path(os.getenv("APPDATA_ROOT", str(HERE_I_AM_ROOT / "appdata")))
QUEUE_ROOT = APPDATA_ROOT / "queue"
JOB_ROOT = APPDATA_ROOT / "jobs"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemma4:e4b")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", CHAT_MODEL)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embeddinggemma")
TRANSCRIPTION_MODEL = os.getenv("TRANSCRIPTION_MODEL", "base")
CHROMA_HOST = os.getenv("CHROMA_HOST", "chroma")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
JOB_POLL_SECONDS = int(os.getenv("JOB_POLL_SECONDS", "3"))
CHUNK_SIZE_WORDS = int(os.getenv("CHUNK_SIZE_WORDS", "220"))
CHUNK_OVERLAP_WORDS = int(os.getenv("CHUNK_OVERLAP_WORDS", "40"))

for path in [QUEUE_ROOT, JOB_ROOT]:
    path.mkdir(parents=True, exist_ok=True)

whisper_model = WhisperModel(
    TRANSCRIPTION_MODEL,
    device="cpu",
    compute_type="int8",
)
chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def session_dir(session_id: str) -> Path:
    return LIBRARY_ROOT / "sessions" / session_id


def update_job(job_id: str, **changes: Any) -> dict[str, Any]:
    path = JOB_ROOT / f"{job_id}.json"
    job = read_json(path)
    job.update(changes)
    job["updated_at"] = utc_now_iso()
    write_json(path, job)
    return job


def update_progress(job_id: str, current: int, total: int, message: str, filename: str | None = None) -> None:
    path = JOB_ROOT / f"{job_id}.json"
    job = read_json(path)
    job["progress"] = {
        "current": current,
        "total": total,
        "message": message,
        "filename": filename,
        "percent": round((current / total) * 100, 2) if total else 0,
    }
    job["updated_at"] = utc_now_iso()
    write_json(path, job)


def update_state(session_id: str, **changes: Any) -> None:
    path = session_dir(session_id) / "processing_state.json"
    state = read_json(path, default={})
    state.update(changes)
    state["updated_at"] = utc_now_iso()
    write_json(path, state)


def clean_text(text: str) -> str:
    text = text.replace("\r", "")
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def make_markdown_transcript(session_id: str, raw_result: dict[str, Any]) -> str:
    full_text = clean_text(raw_result.get("text", ""))
    segments = raw_result.get("segments", [])
    lines = [f"# Session {session_id}", "", "## Transcript", ""]
    if segments:
        for seg in segments:
            start = int(seg.get("start", 0))
            minutes = start // 60
            seconds = start % 60
            stamp = f"[{minutes:02d}:{seconds:02d}]"
            seg_text = clean_text(seg.get("text", ""))
            if seg_text:
                lines.append(f"{stamp} {seg_text}")
                lines.append("")
    else:
        lines.append(full_text)
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def call_ollama_generate(prompt: str, model: str) -> str:
    with httpx.Client(timeout=180) as client:
        response = client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={"model": model, "prompt": prompt, "stream": False},
        )
        response.raise_for_status()
        return response.json().get("response", "")


def call_ollama_embed(inputs: list[str]) -> list[list[float]]:
    with httpx.Client(timeout=180) as client:
        response = client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBEDDING_MODEL, "input": inputs},
        )
        response.raise_for_status()
        data = response.json()
        embeddings = data.get("embeddings") or []
        return embeddings


def get_or_create_collection():
    try:
        return chroma_client.get_collection("here_i_am_chunks")
    except Exception:
        return chroma_client.create_collection(
            name="here_i_am_chunks",
            metadata={"description": "Personal autobiographical transcript chunks for Here I Am."},
        )


def simple_chunk_markdown(md_text: str) -> list[str]:
    no_headers = re.sub(r"^#.*$", "", md_text, flags=re.MULTILINE)
    no_timestamps = re.sub(r"\[(\d{2}:\d{2})\]\s*", "", no_headers)
    words = no_timestamps.split()
    chunks: list[str] = []
    step = max(1, CHUNK_SIZE_WORDS - CHUNK_OVERLAP_WORDS)
    for start in range(0, len(words), step):
        chunk_words = words[start : start + CHUNK_SIZE_WORDS]
        if not chunk_words:
            continue
        chunk = " ".join(chunk_words).strip()
        if chunk:
            chunks.append(chunk)
        if start + CHUNK_SIZE_WORDS >= len(words):
            break
    return chunks


def parse_json_response(text: str) -> dict[str, Any]:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```(?:json)?", "", text).strip()
        text = re.sub(r"```$", "", text).strip()
    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1:
        raise ValueError("No JSON object found in model response")
    return json.loads(text[start : end + 1])


def analyze_transcript(session_id: str, transcript_text: str) -> dict[str, Any]:
    prompt = f"""
You are analyzing a first-person autobiographical transcript from a single speaker.
Return valid JSON only. No markdown. No explanation.

Required JSON schema:
{{
  "session_id": "{session_id}",
  "title": "short descriptive title",
  "summary": "2-4 sentence summary",
  "topics": ["topic1", "topic2"],
  "people": ["person1"],
  "places": ["place1"],
  "time_period": "life period or historical period if inferable",
  "emotional_tone": ["tone1", "tone2"],
  "autobiographical_significance": "why this matters in the speaker's life story",
  "privacy_level": "private",
  "analysis_version": "1.0"
}}

Transcript:
{transcript_text[:16000]}
""".strip()
    response = call_ollama_generate(prompt, ANALYSIS_MODEL)
    data = parse_json_response(response)
    data.setdefault("session_id", session_id)
    data.setdefault("privacy_level", "private")
    data.setdefault("analysis_version", "1.0")
    data["recorded_at"] = session_id.replace("_", "T")
    return data


def transcribe_job(job: dict[str, Any]) -> None:
    session_ids = job["payload"].get("session_ids", [])
    total = len(session_ids)
    update_job(job["job_id"], status="running")
    for idx, sid in enumerate(session_ids, start=1):
        ses_dir = session_dir(sid)
        flac = ses_dir / "recording.flac"
        transcript = ses_dir / "transcript.md"
        update_progress(job["job_id"], idx - 1, total, "Transcribing", flac.name)
        update_state(sid, transcription_status="running")
        segments, info = whisper_model.transcribe(str(flac), vad_filter=True)
        segments = list(segments)
        result = {
            "text": " ".join(seg.text.strip() for seg in segments).strip(),
            "segments": [{"start": seg.start, "text": seg.text} for seg in segments],
        }
        transcript.write_text(make_markdown_transcript(sid, result), encoding="utf-8")
        update_state(sid, transcription_status="complete")
        update_progress(job["job_id"], idx, total, "Saving transcript", transcript.name)
    update_job(job["job_id"], status="complete", result={"detail": "All files transcribed"})
    update_progress(job["job_id"], total, total, "All files transcribed")


def analyze_job(job: dict[str, Any]) -> None:
    session_ids = job["payload"].get("session_ids", [])
    total = len(session_ids)
    update_job(job["job_id"], status="running")
    collection = get_or_create_collection()

    for idx, sid in enumerate(session_ids, start=1):
        ses_dir = session_dir(sid)
        transcript_path = ses_dir / "transcript.md"
        transcript_text = transcript_path.read_text(encoding="utf-8")
        update_progress(job["job_id"], idx - 1, total, "Analyzing transcript", transcript_path.name)
        update_state(sid, analysis_status="running", embedding_status="running")

        metadata = analyze_transcript(sid, transcript_text)
        metadata["source_audio"] = str(ses_dir / "recording.flac")
        metadata["transcript_path"] = str(transcript_path)
        metadata_path = ses_dir / "metadata.json"
        write_json(metadata_path, metadata)

        chunks = simple_chunk_markdown(transcript_text)
        embeddings = call_ollama_embed(chunks)
        ids = [f"{sid}-chunk-{i}" for i in range(len(chunks))]
        metadatas = []
        for i, chunk in enumerate(chunks):
            meta = {
                "session_id": sid,
                "chunk_index": i,
                "title": metadata.get("title", f"Session {sid}"),
                "time_period": metadata.get("time_period", ""),
                "topics": ", ".join(metadata.get("topics", [])),
                "people": ", ".join(metadata.get("people", [])),
                "places": ", ".join(metadata.get("places", [])),
            }
            metadatas.append(meta)

        # remove old chunks for idempotency
        try:
            collection.delete(where={"session_id": sid})
        except Exception:
            pass

        collection.add(ids=ids, documents=chunks, embeddings=embeddings, metadatas=metadatas)

        chunks_path = ses_dir / "chunks.jsonl"
        with chunks_path.open("w", encoding="utf-8") as handle:
            for i, chunk in enumerate(chunks):
                rec = {"id": ids[i], "text": chunk, "metadata": metadatas[i]}
                handle.write(json.dumps(rec) + "\n")

        update_state(sid, analysis_status="complete", embedding_status="complete")
        update_progress(job["job_id"], idx, total, "Embeddings completed", transcript_path.name)

    update_job(job["job_id"], status="complete", result={"detail": "All transcripts analyzed and embedded"})
    update_progress(job["job_id"], total, total, "All transcripts analyzed and embedded")


def run_job(job_id: str) -> None:
    job_path = JOB_ROOT / f"{job_id}.json"
    job = read_json(job_path)
    try:
        if job.get("job_type") == "transcribe":
            transcribe_job(job)
        elif job.get("job_type") == "analyze":
            analyze_job(job)
        else:
            raise ValueError(f"Unsupported job type: {job.get('job_type')}")
    except Exception as exc:
        update_job(job_id, status="failed", error=str(exc))
        progress = read_json(job_path).get("progress", {})
        update_progress(job_id, progress.get("current", 0), progress.get("total", 0), f"Failed: {exc}")


def work_forever() -> None:
    while True:
        queued = sorted(QUEUE_ROOT.glob("*.json"))
        if not queued:
            time.sleep(JOB_POLL_SECONDS)
            continue
        next_item = queued[0]
        try:
            payload = read_json(next_item)
            job_id = payload["job_id"]
            next_item.unlink(missing_ok=True)
            run_job(job_id)
        except Exception:
            next_item.unlink(missing_ok=True)


if __name__ == "__main__":
    work_forever()
