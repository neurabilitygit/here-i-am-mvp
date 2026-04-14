from __future__ import annotations

import shutil
import subprocess
import time
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request

from config import settings
from models.schemas import ChatRequest, ChatResponse, GenericStatus, RecordingUploadResponse
from services.jobs import job_manager
from services.ollama_client import ollama_client
from services.pipeline import analyze_unprocessed, answer_question, transcribe_unprocessed
from services.storage import create_session_dir, ensure_directories, list_session_dirs, session_paths

app = FastAPI(title=settings.app_name)
app.add_middleware(CORSMiddleware, allow_origins=['*'], allow_credentials=True, allow_methods=['*'], allow_headers=['*'])

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')


@app.on_event('startup')
def on_startup() -> None:
    ensure_directories()


@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse('index.html', {'request': request, 'chat_model': settings.ollama_chat_model})


@app.get('/api/health', response_model=GenericStatus)
def health() -> GenericStatus:
    if not Path(settings.data_root).exists():
        raise HTTPException(status_code=500, detail=f'Data root is missing: {settings.data_root}')
    return GenericStatus(status='ok', detail='Application is healthy')


@app.get('/api/ollama/status')
def ollama_status():
    try:
        control = ollama_client.control_status()
    except Exception as exc:
        control = {'status': 'unknown', 'detail': str(exc)}
    reachable = ollama_client.is_reachable()
    return {
        'control': control,
        'api_reachable': reachable,
        'base_url': settings.ollama_base_url,
        'chat_model': settings.ollama_chat_model,
        'embedding_model': settings.ollama_embedding_model,
    }


@app.post('/api/ollama/start')
def start_ollama():
    return ollama_client.start()


@app.post('/api/ollama/stop')
def stop_ollama():
    return ollama_client.stop()


@app.post('/api/recordings/upload', response_model=RecordingUploadResponse)
async def upload_recording(file: UploadFile = File(...), title: str | None = None):
    session_id, session_dir = create_session_dir(title=title)
    source_path = session_dir / f'upload_{file.filename}'
    with source_path.open('wb') as buffer:
        shutil.copyfileobj(file.file, buffer)

    flac_path = session_dir / 'recording.flac'
    command = [
        'ffmpeg', '-y', '-i', str(source_path), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'flac', str(flac_path)
    ]
    completed = subprocess.run(command, capture_output=True, text=True)
    if completed.returncode != 0 or not flac_path.exists():
        source_path.unlink(missing_ok=True)
        try:
            flac_path.unlink(missing_ok=True)
        except Exception:
            pass
        raise HTTPException(status_code=500, detail=f'ffmpeg conversion failed: {completed.stderr}')
    source_path.unlink(missing_ok=True)
    return RecordingUploadResponse(
        session_id=session_id,
        session_path=str(session_dir),
        flac_path=str(flac_path),
        message='Recording saved as FLAC',
    )


@app.get('/api/recordings/summary')
def recording_summary():
    sessions = list_session_dirs()
    total = len(sessions)
    transcribed = 0
    analyzed = 0
    for session in sessions:
        paths = session_paths(session)
        transcribed += int(paths['transcript'].exists())
        analyzed += int(paths['metadata'].exists())
    return {
        'total_sessions': total,
        'transcribed_sessions': transcribed,
        'analyzed_sessions': analyzed,
        'pending_transcription': total - transcribed,
        'pending_analysis': transcribed - analyzed,
    }


@app.post('/api/transcribe/start')
def start_transcribe_job():
    job = job_manager.create(mode='transcribe', message='Queued transcription job')
    job_manager.run_in_thread(job.id, lambda: transcribe_unprocessed(job.id))
    return job


@app.post('/api/analyze/start')
def start_analyze_job():
    job = job_manager.create(mode='analyze', message='Queued analysis job')
    job_manager.run_in_thread(job.id, lambda: analyze_unprocessed(job.id))
    return job


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    return job


@app.post('/api/chat', response_model=ChatResponse)
def chat(payload: ChatRequest):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail='Question is required')

    start = time.time()
    answer = answer_question(payload.question.strip())
    total = time.time() - start
    print(f"[TIMING] total_chat_time={total:.2f}s")

    return ChatResponse(answer=answer)
