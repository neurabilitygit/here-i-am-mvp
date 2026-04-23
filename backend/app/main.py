from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx
import chromadb
from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel


APP_NAME = "Here I Am MVP"
HERE_I_AM_ROOT = Path(os.getenv("HERE_I_AM_ROOT", "/data"))
LIBRARY_ROOT = Path(os.getenv("LIBRARY_ROOT", str(HERE_I_AM_ROOT / "library")))
APPDATA_ROOT = Path(os.getenv("APPDATA_ROOT", str(HERE_I_AM_ROOT / "appdata")))
QUEUE_ROOT = APPDATA_ROOT / "queue"
JOB_ROOT = APPDATA_ROOT / "jobs"
TMP_ROOT = APPDATA_ROOT / "tmp"
LOG_ROOT = APPDATA_ROOT / "logs"
OLLAMA_BASE_URL = os.getenv("OLLAMA_BASE_URL", "http://host.docker.internal:11434")
OLLAMA_CONTROL_URL = os.getenv("OLLAMA_CONTROL_URL", "http://host.docker.internal:11435")
CHAT_MODEL = os.getenv("CHAT_MODEL", "gemma4:e4b")
ANALYSIS_MODEL = os.getenv("ANALYSIS_MODEL", CHAT_MODEL)
EMBEDDING_MODEL = os.getenv("EMBEDDING_MODEL", "embeddinggemma")
TRANSCRIPTION_MODEL = os.getenv("TRANSCRIPTION_MODEL", "base")
CHROMA_HOST = os.getenv("CHROMA_HOST", "chroma")
CHROMA_PORT = int(os.getenv("CHROMA_PORT", "8000"))
CORS_ORIGINS = [x.strip() for x in os.getenv("CORS_ORIGINS", "http://localhost:3000").split(",") if x.strip()]

for path in [LIBRARY_ROOT / "sessions", APPDATA_ROOT, QUEUE_ROOT, JOB_ROOT, TMP_ROOT, LOG_ROOT]:
    path.mkdir(parents=True, exist_ok=True)

chroma_client = chromadb.HttpClient(host=CHROMA_HOST, port=CHROMA_PORT)

app = FastAPI(title=APP_NAME)
app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


class OllamaActionResponse(BaseModel):
    ok: bool
    detail: str
    status: str | None = None


class ChatRequest(BaseModel):
    question: str


class JobStartResponse(BaseModel):
    job_id: str
    detail: str


class RecordStartResponse(BaseModel):
    session_id: str
    session_dir: str


class ConfigResponse(BaseModel):
    root: str
    library_root: str
    appdata_root: str
    chat_model: str
    analysis_model: str
    embedding_model: str
    transcription_model: str


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def session_dir(session_id: str) -> Path:
    return LIBRARY_ROOT / "sessions" / session_id


async def ollama_tags() -> list[dict[str, Any]]:
    async with httpx.AsyncClient(timeout=20) as client:
        response = await client.get(f"{OLLAMA_BASE_URL}/api/tags")
        response.raise_for_status()
        data = response.json()
        return data.get("models", [])


async def ollama_status() -> dict[str, Any]:
    try:
        models = await ollama_tags()
        return {"reachable": True, "status": "ready", "models": models}
    except Exception as exc:  # pragma: no cover - operational path
        return {"reachable": False, "status": "stopped", "detail": str(exc), "models": []}


async def call_ollama_control(action: str) -> OllamaActionResponse:
    try:
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(f"{OLLAMA_CONTROL_URL}/{action}")
            response.raise_for_status()
            data = response.json()
            return OllamaActionResponse(**data)
    except Exception as exc:
        return OllamaActionResponse(
            ok=False,
            detail=(
                "Ollama control helper is unavailable. The main app is containerized, but native macOS Ollama "
                "cannot be started or stopped directly from inside Docker. Start the helper in host_tools/ollama_control.py "
                f"or manage Ollama manually. Underlying error: {exc}"
            ),
            status="unknown",
        )


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.write_text(json.dumps(data, indent=2), encoding="utf-8")


def read_json(path: Path, default: dict[str, Any] | None = None) -> dict[str, Any]:
    if not path.exists():
        return default or {}
    return json.loads(path.read_text(encoding="utf-8"))


def create_job(job_type: str, payload: dict[str, Any]) -> str:
    job_id = str(uuid.uuid4())
    job = {
        "job_id": job_id,
        "job_type": job_type,
        "status": "queued",
        "created_at": utc_now_iso(),
        "updated_at": utc_now_iso(),
        "payload": payload,
        "progress": {"current": 0, "total": 0, "message": "Queued"},
        "result": {},
        "error": None,
    }
    write_json(JOB_ROOT / f"{job_id}.json", job)
    write_json(QUEUE_ROOT / f"{job_id}.json", {"job_id": job_id})
    return job_id


def list_sessions() -> list[Path]:
    sessions_root = LIBRARY_ROOT / "sessions"
    if not sessions_root.exists():
        return []
    return sorted([p for p in sessions_root.iterdir() if p.is_dir()])


def compute_library_summary() -> dict[str, Any]:
    sessions = list_sessions()
    audio_count = 0
    transcript_count = 0
    metadata_count = 0
    indexed_count = 0
    for session in sessions:
        if (session / "recording.flac").exists():
            audio_count += 1
        if (session / "transcript.md").exists():
            transcript_count += 1
        if (session / "metadata.json").exists():
            metadata_count += 1
        state = read_json(session / "processing_state.json", default={})
        if state.get("embedding_status") == "complete":
            indexed_count += 1
    return {
        "sessions": len(sessions),
        "audio_files": audio_count,
        "transcripts": transcript_count,
        "metadata": metadata_count,
        "indexed": indexed_count,
    }


def sessions_missing_transcripts() -> list[dict[str, Any]]:
    out = []
    for session in list_sessions():
        flac = session / "recording.flac"
        transcript = session / "transcript.md"
        if flac.exists() and not transcript.exists():
            out.append({"session_id": session.name, "filename": flac.name})
    return out


def sessions_missing_analysis() -> list[dict[str, Any]]:
    out = []
    for session in list_sessions():
        transcript = session / "transcript.md"
        metadata = session / "metadata.json"
        state = read_json(session / "processing_state.json", default={})
        needs_embeddings = state.get("embedding_status") != "complete"
        if transcript.exists() and (not metadata.exists() or needs_embeddings):
            out.append({"session_id": session.name, "filename": transcript.name})
    return out


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"ok": True, "app": APP_NAME, "time": utc_now_iso()}


@app.get("/api/config", response_model=ConfigResponse)
def config() -> ConfigResponse:
    return ConfigResponse(
        root=str(HERE_I_AM_ROOT),
        library_root=str(LIBRARY_ROOT),
        appdata_root=str(APPDATA_ROOT),
        chat_model=CHAT_MODEL,
        analysis_model=ANALYSIS_MODEL,
        embedding_model=EMBEDDING_MODEL,
        transcription_model=TRANSCRIPTION_MODEL,
    )


@app.get("/api/library/summary")
def library_summary() -> dict[str, Any]:
    return compute_library_summary()


@app.get("/api/ollama/status")
async def get_ollama_status() -> dict[str, Any]:
    return await ollama_status()


@app.post("/api/ollama/start", response_model=OllamaActionResponse)
async def start_ollama() -> OllamaActionResponse:
    return await call_ollama_control("start")


@app.post("/api/ollama/stop", response_model=OllamaActionResponse)
async def stop_ollama() -> OllamaActionResponse:
    return await call_ollama_control("stop")


@app.post("/api/record/start", response_model=RecordStartResponse)
def record_start() -> RecordStartResponse:
    session_id = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = session_dir(session_id)
    path.mkdir(parents=True, exist_ok=False)
    write_json(
        path / "processing_state.json",
        {
            "session_id": session_id,
            "recording_status": "recording",
            "transcription_status": "not_started",
            "analysis_status": "not_started",
            "embedding_status": "not_started",
            "created_at": utc_now_iso(),
            "updated_at": utc_now_iso(),
        },
    )
    write_json(path / "session.json", {"session_id": session_id, "created_at": utc_now_iso()})
    return RecordStartResponse(session_id=session_id, session_dir=str(path))


@app.post("/api/record/pause")
def record_pause(session_id: str = Form(...)) -> dict[str, Any]:
    path = session_dir(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    state = read_json(path / "processing_state.json", default={})
    state["recording_status"] = "paused"
    state["updated_at"] = utc_now_iso()
    write_json(path / "processing_state.json", state)
    return {"ok": True, "status": "paused"}


@app.post("/api/record/resume")
def record_resume(session_id: str = Form(...)) -> dict[str, Any]:
    path = session_dir(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Session not found")
    state = read_json(path / "processing_state.json", default={})
    state["recording_status"] = "recording"
    state["updated_at"] = utc_now_iso()
    write_json(path / "processing_state.json", state)
    return {"ok": True, "status": "recording"}


@app.post("/api/record/stop")
async def record_stop(session_id: str = Form(...), audio: UploadFile = File(...)) -> dict[str, Any]:
    path = session_dir(session_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="Session not found")

    temp_input = TMP_ROOT / f"{session_id}_{audio.filename or 'capture.webm'}"
    with temp_input.open("wb") as file_handle:
        shutil.copyfileobj(audio.file, file_handle)

    flac_path = path / "recording.flac"
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        str(temp_input),
        "-ac",
        "1",
        "-ar",
        "44100",
        str(flac_path),
    ]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    temp_input.unlink(missing_ok=True)
    if proc.returncode != 0:
        raise HTTPException(status_code=500, detail=f"ffmpeg conversion failed: {proc.stderr}")

    state = read_json(path / "processing_state.json", default={})
    state["recording_status"] = "complete"
    state["updated_at"] = utc_now_iso()
    write_json(path / "processing_state.json", state)
    return {"ok": True, "session_id": session_id, "file": str(flac_path)}


@app.get("/api/transcribe/summary")
def transcribe_summary() -> dict[str, Any]:
    items = sessions_missing_transcripts()
    return {"count": len(items), "items": items}


@app.post("/api/transcribe/start", response_model=JobStartResponse)
def transcribe_start() -> JobStartResponse:
    pending = sessions_missing_transcripts()
    if not pending:
        raise HTTPException(status_code=400, detail="No new recordings require transcription")
    job_id = create_job("transcribe", {"session_ids": [x["session_id"] for x in pending]})
    return JobStartResponse(job_id=job_id, detail="Transcription job queued")


@app.get("/api/analysis/summary")
def analysis_summary() -> dict[str, Any]:
    items = sessions_missing_analysis()
    return {"count": len(items), "items": items}


@app.post("/api/analysis/start", response_model=JobStartResponse)
def analysis_start() -> JobStartResponse:
    pending = sessions_missing_analysis()
    if not pending:
        raise HTTPException(status_code=400, detail="No new transcripts require analysis")
    job_id = create_job("analyze", {"session_ids": [x["session_id"] for x in pending]})
    return JobStartResponse(job_id=job_id, detail="Analysis job queued")


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, Any]:
    path = JOB_ROOT / f"{job_id}.json"
    if not path.exists():
        raise HTTPException(status_code=404, detail="Job not found")
    return read_json(path)


@app.post("/api/chat")
async def chat(request: ChatRequest) -> dict[str, Any]:
    if not request.question.strip():
        raise HTTPException(status_code=400, detail="Question cannot be empty")

    async with httpx.AsyncClient(timeout=120) as client:
        embed_resp = await client.post(
            f"{OLLAMA_BASE_URL}/api/embed",
            json={"model": EMBEDDING_MODEL, "input": request.question},
        )
        embed_resp.raise_for_status()
        embed_json = embed_resp.json()
        embeddings = embed_json.get("embeddings") or []
        if not embeddings:
            raise HTTPException(status_code=500, detail="Embedding model returned no vector")
        query_embedding = embeddings[0]

        try:
            collection = chroma_client.get_collection("here_i_am_chunks")
        except Exception:
            return {"answer": "The knowledge library has not been indexed yet.", "context_count": 0}
        chroma = collection.query(
            query_embeddings=[query_embedding],
            n_results=int(os.getenv("MAX_CHAT_CONTEXT_CHUNKS", "6")),
            include=["documents", "metadatas", "distances"],
        )

        docs = (chroma.get("documents") or [[]])[0]
        metas = (chroma.get("metadatas") or [[]])[0]
        context_blocks = []
        for idx, doc in enumerate(docs):
            meta = metas[idx] if idx < len(metas) else {}
            label = f"Session {meta.get('session_id', 'unknown')} | {meta.get('title', 'Untitled')} | chunk {meta.get('chunk_index', idx)}"
            context_blocks.append(f"[{label}]\n{doc}")

        context = "\n\n".join(context_blocks)
        system_prompt = (
            "You are Here I Am, a personal memory assistant. Answer concisely and directly from the retrieved autobiographical "
            "material. Do not quote source passages or mention chunks. Do not invent facts. If the answer is not grounded in the "
            "retrieved material, say that the library does not currently contain enough information. Do not ramble. Try hard to answer the question."
        )
        user_prompt = f"Retrieved memory context:\n\n{context}\n\nUser question: {request.question}"

        gen_resp = await client.post(
            f"{OLLAMA_BASE_URL}/api/generate",
            json={
                "model": CHAT_MODEL,
                "prompt": f"System: {system_prompt}\n\nUser: {user_prompt}\n\nAssistant:",
                "stream": False,
            },
        )
        gen_resp.raise_for_status()
        data = gen_resp.json()
        answer = data.get("response", "")
        return {"answer": answer, "context_count": len(docs)}


@app.exception_handler(Exception)
async def unhandled_exception_handler(_, exc: Exception) -> JSONResponse:  # pragma: no cover - operational path
    return JSONResponse(status_code=500, content={"detail": str(exc)})
