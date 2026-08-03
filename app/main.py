from __future__ import annotations

import asyncio
import shutil
import subprocess
import time
import json
import logging
import queue
from contextlib import asynccontextmanager
import requests
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Query, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.trustedhost import TrustedHostMiddleware
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, Response, StreamingResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi import Request
from fastapi.concurrency import run_in_threadpool
from starlette.background import BackgroundTask

from config import settings
from models.schemas import AnswerFeedback, AuthLoginRequest, AuthStatus, AvatarGenerationRequest, AvatarJobResponse, ChatBenchmarkResponse, ChatRequest, ChatResponse, ClientActivityEvent, GenericStatus, PreferencesUpdate, ProviderStatus, PromptOfTheDay, QuizPrompt, RecordingUploadResponse, ReconciliationReport, SealRequest, SessionDetail, SessionSummary, SpeakerAssignmentsUpdate, SpeakerCreate, SpeakerProfile, TranscriptUpdate, TTSRequest, VoicePrepareRequest, VoiceStatus
from services.prompts import prompt_of_the_day
from services.auth import SESSION_COOKIE_NAME, is_locked_out, issue_token, passphrase_configured, register_failure, register_success, requires_auth, revoke_token, validate_token, verify_passphrase
from services.jobs import JobConflictError, job_manager
from services.library import build_session_export, create_structured_backup, days_since_last_recording, get_session, is_sealed, list_sessions, on_this_day_sessions, reconciliation_report, sealed_sessions
from services.ollama_client import ollama_client
from services.fidelity import build_speaker_fingerprint, load_speaker_fingerprint, save_answer_feedback
from services.pipeline import analyze_unprocessed, answer_question, benchmark_question, memory_queue_status, prepare_answer, process_memory_batch, reindex_to_migration_collection, related_sessions, sample_quiz_prompt, stream_prepared_answer, transcribe_unprocessed
from services.preferences import cloud_api_key, load_preferences, public_preferences, save_preferences, set_runtime_cloud_key
from services.providers import active_provider, provider_status, public_provider_error, record_generation_failure, record_stream_audit, transition_provider, validate_provider_selection
from services.storage import archive_session, create_session_dir, ensure_directories, list_session_dirs, revise_transcript, safe_session_dir, seal_until, session_lock, session_paths, update_processing_state
from services.speakers import SpeakerWorkflowError, apply_speaker_assignments, create_speaker, list_speakers, speaker_review, speaker_sample
from services.avatars import AvatarWorkflowError, active_avatar_path, generate_avatar, store_speaker_image, validate_avatar_generation
from services.voice import LOCAL_BRIDGE_HEADERS, cancel_synthesis_stream, list_voice_candidates, load_voice_status, prepare_voice_reference, public_voice_error, revoke_voice, synthesize
from services.activity import recent_activity, record_activity

@asynccontextmanager
async def lifespan(_app: FastAPI):
    ensure_directories()
    if not Path(settings.fidelity_profile_path).exists():
        threading.Thread(target=build_speaker_fingerprint, name='speaker-fingerprint', daemon=True).start()
    if ollama_client.is_reachable():
        preferences = load_preferences()
        def prepare_ollama():
            if preferences.provider == 'local':
                ollama_client.preload()
            else:
                ollama_client.unload_chat()
            ollama_client.unload_embeddings()
        threading.Thread(target=prepare_ollama, name='ollama-preload', daemon=True).start()
    yield


app = FastAPI(
    title=settings.app_name,
    lifespan=lifespan,
    docs_url='/docs' if settings.api_docs_enabled else None,
    redoc_url='/redoc' if settings.api_docs_enabled else None,
    openapi_url='/openapi.json' if settings.api_docs_enabled else None,
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=['GET', 'POST', 'PUT'],
    allow_headers=['Content-Type'],
)
logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO))
logger = logging.getLogger('here_i_am')

BASE_DIR = Path(__file__).resolve().parent
templates = Jinja2Templates(directory=str(BASE_DIR / 'templates'))
app.mount('/static', StaticFiles(directory=str(BASE_DIR / 'static')), name='static')


@app.middleware('http')
async def request_observability(request: Request, call_next):
    started = time.perf_counter()
    request_id = request.headers.get('X-Request-ID', '')
    if not request_id or len(request_id) > 80 or not request_id.replace('-', '').replace('_', '').isalnum():
        request_id = str(uuid.uuid4())
    request.state.request_id = request_id
    origin = request.headers.get('origin')
    batch_allowed = (
        request.method == 'GET'
        or request.url.path == '/api/memory-batch/start'
        or request.url.path == '/api/activity-events'
        or request.url.path.startswith('/api/voice/cancel/')
        or request.url.path in {'/api/auth/login', '/api/auth/logout'}
    )
    session_token = request.cookies.get(SESSION_COOKIE_NAME, '')
    if requires_auth(request.method, request.url.path) and not validate_token(session_token):
        response = JSONResponse(status_code=401, content={'detail': 'Authentication required'})
    elif request.method in {'POST', 'PUT', 'PATCH', 'DELETE'} and origin and origin not in settings.cors_origin_list:
        response = JSONResponse(status_code=403, content={'detail': 'Cross-origin changes are not allowed'})
    elif job_manager.is_active('memory-batch') and request.url.path.startswith('/api/') and not batch_allowed:
        response = JSONResponse(
            status_code=423,
            content={'detail': 'Local memory processing is running. Here I Am will be available when the batch finishes.'},
        )
    else:
        try:
            response = await call_next(request)
        except Exception:
            logger.exception('unhandled request failure request_id=%s path=%s', request_id, request.url.path)
            response = JSONResponse(status_code=500, content={'detail': 'Here I Am encountered an unexpected local error.'})
    elapsed = time.perf_counter() - started
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'DENY'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Permissions-Policy'] = 'camera=(), geolocation=(), payment=(), usb=()'
    response.headers['Content-Security-Policy'] = (
        "default-src 'self'; img-src 'self' data:; media-src 'self' blob:; "
        "script-src 'self'; style-src 'self' 'unsafe-inline'; connect-src 'self'; "
        "frame-ancestors 'none'; base-uri 'self'; form-action 'self'"
    )
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Request-ID'] = request_id
    logger.info('request id=%s method=%s path=%s status=%s elapsed=%.3f', request_id, request.method, request.url.path, response.status_code, elapsed)
    return response


@app.get('/', response_class=HTMLResponse)
def home(request: Request):
    return templates.TemplateResponse(request, 'index.html', {'chat_model': settings.ollama_chat_model})


@app.get('/api/health', response_model=GenericStatus)
def health() -> GenericStatus:
    if not Path(settings.data_root).exists():
        raise HTTPException(status_code=500, detail=f'Data root is missing: {settings.data_root}')
    return GenericStatus(status='ok', detail='Application is healthy')


@app.post('/api/auth/login', response_model=AuthStatus)
def login(payload: AuthLoginRequest, response: Response):
    if is_locked_out():
        raise HTTPException(status_code=429, detail='Too many attempts. Try again later.')
    if not passphrase_configured() or not verify_passphrase(payload.passphrase):
        register_failure()
        raise HTTPException(status_code=401, detail='Incorrect passphrase')
    register_success()
    token = issue_token(label='device')
    response.set_cookie(
        key=SESSION_COOKIE_NAME,
        value=token,
        max_age=settings.auth_token_ttl_seconds,
        httponly=True,
        # Not `secure`: Tailscale's `serve` terminates HTTPS externally but
        # forwards plain HTTP to this app internally, and local access is
        # plain http://127.0.0.1 too. Transport confidentiality comes from
        # loopback binding and Tailscale's WireGuard tunnel, not app-level
        # TLS; a `Secure` cookie would be silently dropped by strict clients
        # (observed: Safari over http://127.0.0.1 never persisted the
        # session, making every post-login request 401 and re-show login).
        samesite='lax',
        path='/',
    )
    return AuthStatus(authenticated=True, required=True)


@app.get('/api/auth/status', response_model=AuthStatus)
def auth_status(request: Request):
    return AuthStatus(
        authenticated=validate_token(request.cookies.get(SESSION_COOKIE_NAME, '')),
        required=passphrase_configured(),
    )


@app.post('/api/auth/logout', response_model=GenericStatus)
def logout(request: Request, response: Response):
    revoke_token(request.cookies.get(SESSION_COOKIE_NAME, ''))
    response.delete_cookie(SESSION_COOKIE_NAME, path='/')
    return GenericStatus(status='ok', detail='Logged out')


@app.get('/api/version')
def version():
    return {
        'commit': settings.app_build_commit,
        'build_date': settings.app_build_date,
    }


@app.get('/api/prompts/today', response_model=PromptOfTheDay)
def prompt_today():
    return PromptOfTheDay(prompt=prompt_of_the_day())


@app.get('/api/quiz/prompt', response_model=QuizPrompt | None)
def quiz_prompt():
    return sample_quiz_prompt()


@app.post('/api/activity-events', status_code=202)
def post_activity_event(payload: ClientActivityEvent, request: Request):
    record_activity(payload, request_id=getattr(request.state, 'request_id', ''))
    return {'status': 'accepted'}


@app.get('/api/activity-events')
def get_activity_events(limit: int = Query(default=100, ge=1, le=500)):
    return {'events': recent_activity(limit)}


@app.get('/api/ready', response_model=GenericStatus)
def ready() -> GenericStatus:
    if not ollama_client.is_reachable():
        raise HTTPException(status_code=503, detail='Ollama API is unavailable')
    if not ollama_client.has_model(ollama_client.embedding_model):
        raise HTTPException(status_code=503, detail='The local embedding model is not installed')
    if not provider_status()['active_ready']:
        raise HTTPException(status_code=503, detail='The selected answer engine is not ready')
    return GenericStatus(status='ok', detail='Application, retrieval, and selected answer engine are ready')


@app.get('/api/experience')
def experience_preferences():
    return public_preferences()


@app.put('/api/experience')
def update_experience(payload: PreferencesUpdate):
    previous = load_preferences()
    selection_changed = (
        previous.provider != payload.preferences.provider
        or previous.cloud_model != payload.preferences.cloud_model
    )
    if selection_changed or payload.cloud_api_key is not None:
        proposed_key = payload.cloud_api_key if payload.cloud_api_key is not None else cloud_api_key()[0]
        try:
            validate_provider_selection(payload.preferences, proposed_key)
            set_runtime_cloud_key(payload.cloud_api_key)
        except RuntimeError as exc:
            raise HTTPException(status_code=409, detail=str(exc)) from exc
    save_preferences(payload.preferences)
    if previous.provider != payload.preferences.provider:
        threading.Thread(
            target=transition_provider,
            args=(previous.provider, payload.preferences.provider),
            name='provider-transition',
            daemon=True,
        ).start()
    return public_preferences()


@app.get('/api/providers/status', response_model=ProviderStatus)
def get_provider_status():
    return provider_status()


@app.post('/api/providers/local/warm')
def warm_local_provider():
    if not ollama_client.is_reachable():
        raise HTTPException(status_code=503, detail='Local AI is not running')
    return {'status': 'ready' if ollama_client.preload() else 'unavailable'}


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
async def upload_recording(
    file: UploadFile = File(...),
    title: str | None = Form(default=None),
    recording_mode: str = Form(default='solo'),
):
    if title and len(title.strip()) > 160:
        raise HTTPException(status_code=422, detail='Recording title is too long')
    if recording_mode not in {'solo', 'conversation'}:
        raise HTTPException(status_code=422, detail='Recording mode must be solo or conversation')
    session_id, session_dir = create_session_dir(title=title)
    source_path = session_paths(session_dir)['source_audio']
    update_processing_state(
        session_dir,
        recording_mode=recording_mode,
        original_filename=file.filename or '',
        original_content_type=file.content_type or '',
        speaker_processing_status='pending' if recording_mode == 'conversation' else 'not_required',
        speaker_review_status='pending' if recording_mode == 'conversation' else 'not_required',
    )
    total = 0
    try:
        with source_path.open('wb') as buffer:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_upload_bytes:
                    raise HTTPException(status_code=413, detail='Recording exceeds the configured upload limit')
                buffer.write(chunk)
    except Exception:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise

    flac_path = session_dir / 'recording.flac'
    command = [
        'ffmpeg', '-y', '-i', str(source_path), '-vn', '-ac', '1', '-ar', '16000', '-c:a', 'flac', str(flac_path)
    ]
    try:
        completed = await run_in_threadpool(
            subprocess.run,
            command,
            capture_output=True,
            text=True,
            timeout=900,
        )
    except subprocess.TimeoutExpired as exc:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=408, detail='The uploaded recording took too long to validate') from exc
    if completed.returncode != 0 or not flac_path.exists():
        source_path.unlink(missing_ok=True)
        try:
            flac_path.unlink(missing_ok=True)
        except Exception:
            pass
        shutil.rmtree(session_dir, ignore_errors=True)
        logger.error('ffmpeg conversion failed for session=%s: %s', session_id, completed.stderr[-2000:])
        raise HTTPException(status_code=422, detail='The uploaded file could not be converted to audio')
    probe = ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(flac_path)]
    try:
        duration_result = await run_in_threadpool(
            subprocess.run,
            probe,
            capture_output=True,
            text=True,
            timeout=30,
        )
        duration = float(json.loads(duration_result.stdout)['format']['duration'])
    except (subprocess.TimeoutExpired, KeyError, ValueError, json.JSONDecodeError) as exc:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=422, detail='The uploaded audio duration could not be verified') from exc
    if duration <= 0 or duration > settings.max_upload_seconds:
        shutil.rmtree(session_dir, ignore_errors=True)
        raise HTTPException(status_code=413, detail='The recording duration exceeds the configured limit')
    update_processing_state(session_dir, duration_seconds=round(duration, 3), source_bytes=total)
    return RecordingUploadResponse(
        session_id=session_id,
        message=(
            'Conversation saved and waiting for speaker recognition'
            if recording_mode == 'conversation'
            else 'Recording saved and waiting for local transcription'
        ),
        recording_mode=recording_mode,
    )


@app.get('/api/speakers', response_model=list[SpeakerProfile])
def get_speakers():
    return list_speakers()


@app.post('/api/speakers', response_model=SpeakerProfile)
def post_speaker(payload: SpeakerCreate):
    return create_speaker(payload)


@app.get('/api/sessions/{session_id}/speaker-review')
def get_speaker_review(session_id: str):
    session_dir = safe_session_dir(session_id)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail='Session does not exist')
    try:
        return speaker_review(session_dir)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.put('/api/sessions/{session_id}/speaker-assignments')
async def put_speaker_assignments(session_id: str, payload: SpeakerAssignmentsUpdate):
    session_dir = safe_session_dir(session_id)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail='Session does not exist')
    try:
        return await run_in_threadpool(
            apply_speaker_assignments,
            session_dir,
            [assignment.model_dump(mode='json') for assignment in payload.assignments],
        )
    except (SpeakerWorkflowError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@app.get('/api/sessions/{session_id}/speaker-samples/{cluster_id}')
async def get_speaker_sample(session_id: str, cluster_id: str):
    session_dir = safe_session_dir(session_id)
    if not session_dir.exists():
        raise HTTPException(status_code=404, detail='Session does not exist')
    try:
        path = await run_in_threadpool(speaker_sample, session_dir, cluster_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except SpeakerWorkflowError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return FileResponse(path, media_type='audio/wav', filename=f'{cluster_id}.wav')


@app.post('/api/speakers/{speaker_id}/avatar/upload')
async def upload_speaker_avatar(
    speaker_id: str,
    file: UploadFile = File(...),
    kind: str = Form(default='avatar'),
):
    if kind not in {'avatar', 'photo'}:
        raise HTTPException(status_code=422, detail='Choose avatar or photo')
    try:
        from services.speakers import get_speaker_record

        get_speaker_record(speaker_id)
    except (KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail='Speaker does not exist') from exc
    temporary = Path(settings.tmp_dir) / f'avatar-upload-{uuid.uuid4().hex}.bin'
    total = 0
    try:
        with temporary.open('wb') as handle:
            while chunk := await file.read(1024 * 1024):
                total += len(chunk)
                if total > settings.max_avatar_upload_bytes:
                    raise HTTPException(status_code=413, detail='Image exceeds the configured upload limit')
                handle.write(chunk)
        return await run_in_threadpool(
            store_speaker_image,
            speaker_id,
            temporary,
            kind=kind,
            original_name=file.filename or 'image',
        )
    except AvatarWorkflowError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    finally:
        temporary.unlink(missing_ok=True)


@app.post('/api/speakers/{speaker_id}/avatar/generate', response_model=AvatarJobResponse)
def generate_speaker_avatar(speaker_id: str, payload: AvatarGenerationRequest):
    if not payload.confirm_image_rights:
        raise HTTPException(status_code=422, detail='Confirm that you may use this face photo')
    try:
        validate_avatar_generation(speaker_id)
        job = job_manager.create(mode=f'avatar-{speaker_id}', message='Queued avatar illustration')
    except KeyError as exc:
        raise HTTPException(status_code=404, detail='Speaker does not exist') from exc
    except AvatarWorkflowError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except (ValueError, JobConflictError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job_manager.run_in_thread(job.id, lambda: generate_avatar(job.id, speaker_id))
    return AvatarJobResponse(job_id=job.id, status=job.status, detail=job.message)


@app.get('/api/speakers/{speaker_id}/avatar')
def get_speaker_avatar(speaker_id: str):
    try:
        path = active_avatar_path(speaker_id)
    except (FileNotFoundError, KeyError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(path, media_type='image/webp')


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
    try:
        job = job_manager.create(mode='transcribe', message='Queued transcription job')
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job_manager.run_in_thread(job.id, lambda: transcribe_unprocessed(job.id))
    return job


def _start_memory_batch():
    if job_manager.is_active():
        active = job_manager.active_job('memory-batch')
        if active:
            return active
        raise HTTPException(status_code=409, detail='Another local processing job is already active')
    try:
        job = job_manager.create(mode='memory-batch', message='Queued local memory batch')
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    job_manager.run_in_thread(job.id, lambda: process_memory_batch(job.id))
    return job


@app.get('/api/memory-batch/status')
def get_memory_batch_status():
    return memory_queue_status()


@app.post('/api/memory-batch/start')
def start_memory_batch(confirm: bool = Query(default=False)):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail='Confirm that Here I Am may be unavailable until the local Gemma batch finishes',
        )
    return _start_memory_batch()


@app.post('/api/analyze/start')
def start_analyze_job(confirm: bool = Query(default=False)):
    """Compatibility route; analysis and embedding can only run as a confirmed local batch."""
    if not confirm:
        raise HTTPException(status_code=400, detail='Use the confirmed local memory batch to analyze and embed recordings')
    return _start_memory_batch()


@app.get('/api/jobs/{job_id}')
def get_job(job_id: str):
    job = job_manager.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail='Job not found')
    return job


@app.get('/api/jobs')
def list_jobs(limit: int = Query(default=50, ge=1, le=200)):
    return job_manager.list(limit=limit)


@app.post('/api/chat', response_model=ChatResponse)
def chat(payload: ChatRequest):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail='Question is required')

    status = provider_status()
    if not status['active_ready']:
        raise HTTPException(status_code=503, detail='The selected answer engine is not ready. Check Settings.')
    start = time.time()
    try:
        answer = answer_question(payload.question.strip())
    except Exception as exc:
        logger.exception('chat failed')
        record_generation_failure(status['active'], status.get('cloud_model') or status.get('local_model', ''), time.time() - start, exc)
        raise HTTPException(status_code=503, detail=public_provider_error(status['active'], exc)) from exc
    total = time.time() - start
    print(f"[TIMING] total_chat_time={total:.2f}s")

    answer.elapsed_seconds = total
    return answer


@app.post('/api/chat/stream')
def chat_stream(payload: ChatRequest):
    if not payload.question.strip():
        raise HTTPException(status_code=400, detail='Question is required')
    status = provider_status()
    if not status['active_ready']:
        raise HTTPException(status_code=503, detail='The selected answer engine is not ready. Check Settings.')

    def events():
        started = time.perf_counter()
        prepared = prepare_answer(payload.question.strip())
        current_provider = active_provider()
        direct_answer = getattr(prepared, 'direct_answer', None)
        response_provider = 'memory' if direct_answer is not None else current_provider.name
        yield f'event: meta\ndata: {json.dumps({"mode": prepared.mode, "sources": [source.model_dump(mode="json") for source in prepared.sources], "provider": response_provider, "retrieval_seconds": prepared.retrieval_seconds})}\n\n'
        if direct_answer is not None:
            elapsed = time.perf_counter() - started
            yield f'event: token\ndata: {json.dumps({"text": direct_answer})}\n\n'
            yield f'event: done\ndata: {json.dumps({"elapsed_seconds": elapsed, "first_token_seconds": elapsed, "characters": len(direct_answer)})}\n\n'
            return
        first_token = None
        answer_parts = []
        output: queue.Queue[tuple[str, object]] = queue.Queue()
        canceled = threading.Event()

        def produce() -> None:
            stream = None
            try:
                stream = current_provider.stream(prepared.prompt)
                for token in stream:
                    if canceled.is_set():
                        break
                    output.put(('token', token))
            except Exception as exc:
                output.put(('error', exc))
            finally:
                if stream is not None and hasattr(stream, 'close'):
                    try:
                        stream.close()
                    except Exception:
                        pass
                output.put(('done', None))

        threading.Thread(target=produce, name=f'chat-{current_provider.name}', daemon=True).start()
        failed = False
        try:
            while True:
                try:
                    event, value = output.get(timeout=settings.provider_stream_heartbeat_seconds)
                except queue.Empty:
                    yield ': keep-alive\n\n'
                    continue
                if event == 'token':
                    token = str(value)
                    if first_token is None:
                        first_token = time.perf_counter() - started
                    answer_parts.append(token)
                    yield f'event: token\ndata: {json.dumps({"text": token})}\n\n'
                elif event == 'error':
                    failed = True
                    record_generation_failure(
                        current_provider.name,
                        getattr(current_provider, 'model', ollama_client.chat_model),
                        time.perf_counter() - started,
                        value,
                    )
                    logger.error(
                        'streaming chat failed provider=%s exception=%s',
                        current_provider.name,
                        type(value).__name__,
                        exc_info=(type(value), value, value.__traceback__),
                    )
                    detail = public_provider_error(current_provider.name, value)
                    yield f'event: error\ndata: {json.dumps({"detail": detail})}\n\n'
                elif event == 'done':
                    break
        finally:
            canceled.set()

        if not failed:
            elapsed = time.perf_counter() - started
            record_stream_audit(
                current_provider.name,
                getattr(current_provider, 'model', ollama_client.chat_model),
                elapsed,
                sum(len(value) for value in answer_parts),
                response_id=getattr(current_provider, 'last_response_id', ''),
                usage=getattr(current_provider, 'last_usage', {}),
            )
            yield f'event: done\ndata: {json.dumps({"elapsed_seconds": elapsed, "first_token_seconds": first_token, "characters": sum(len(value) for value in answer_parts)})}\n\n'

    return StreamingResponse(events(), media_type='text/event-stream', headers={'X-Accel-Buffering': 'no'})


@app.post('/api/chat/benchmark', response_model=ChatBenchmarkResponse)
def chat_benchmark(payload: ChatRequest):
    try:
        return benchmark_question(payload.question.strip())
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except requests.RequestException as exc:
        logger.exception('talk benchmark provider failed')
        raise HTTPException(status_code=503, detail='One of the comparison providers is unavailable') from exc


@app.get('/api/fidelity/profile')
def fidelity_profile():
    return load_speaker_fingerprint()


@app.post('/api/fidelity/rebuild')
def rebuild_fidelity_profile():
    return build_speaker_fingerprint()


@app.post('/api/fidelity/feedback')
def answer_feedback(payload: AnswerFeedback):
    return save_answer_feedback(payload)


@app.get('/api/voice/status', response_model=VoiceStatus)
def voice_status():
    return load_voice_status()


@app.get('/api/voice/candidates')
def voice_candidates():
    return list_voice_candidates()


@app.post('/api/voice/prepare', response_model=VoiceStatus)
def prepare_voice(payload: VoicePrepareRequest):
    try:
        return prepare_voice_reference(payload)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post('/api/voice/revoke', response_model=VoiceStatus)
def revoke_synthetic_voice(delete_reference: bool = Query(default=True)):
    return revoke_voice(delete_reference=delete_reference)


@app.post('/api/voice/cache/clear', response_model=GenericStatus)
def clear_voice_cache():
    try:
        response = requests.post(
            f'{settings.voice_bridge_url.rstrip("/")}/cache/clear',
            headers=LOCAL_BRIDGE_HEADERS,
            timeout=20,
        )
        response.raise_for_status()
    except requests.RequestException as exc:
        raise HTTPException(status_code=503, detail='The local voice cache could not be cleared') from exc
    return GenericStatus(status='cleared', detail='Prepared voice files were removed. Your voice reference remains ready.')


@app.post('/api/voice/speak')
async def speak(payload: TTSRequest, request: Request):
    if not payload.request_id:
        payload = payload.model_copy(update={'request_id': uuid.uuid4().hex})
    synthesis = asyncio.create_task(asyncio.to_thread(synthesize, payload.text, payload.speed, payload.request_id))
    async def wait_for_disconnect() -> None:
        while True:
            message = await request.receive()
            if message.get('type') == 'http.disconnect':
                return

    disconnected = asyncio.create_task(wait_for_disconnect())
    try:
        completed, _pending = await asyncio.wait(
            {synthesis, disconnected}, return_when=asyncio.FIRST_COMPLETED,
        )
        if disconnected in completed and not synthesis.done():
            cancel_synthesis_stream(payload.request_id)
            try:
                await asyncio.wait_for(asyncio.shield(synthesis), timeout=5)
            except asyncio.TimeoutError:
                def consume_canceled_synthesis(task: asyncio.Task) -> None:
                    try:
                        task.result()
                    except BaseException:
                        pass
                synthesis.add_done_callback(consume_canceled_synthesis)
            except Exception:
                pass
            return Response(status_code=499)
        audio, media_type, provider = await synthesis
    except asyncio.CancelledError:
        cancel_synthesis_stream(payload.request_id)
        raise
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except requests.RequestException as exc:
        logger.exception('voice synthesis failed')
        raise HTTPException(status_code=503, detail=public_voice_error(load_voice_status().provider, exc)) from exc
    finally:
        disconnected.cancel()
    return Response(audio, media_type=media_type, headers={'X-Voice-Provider': provider, 'Cache-Control': 'no-store'})


@app.post('/api/voice/cancel/{request_id}', response_model=GenericStatus)
def cancel_voice(request_id: str):
    if not request_id or len(request_id) > 80 or not request_id.replace('-', '').replace('_', '').isalnum():
        raise HTTPException(status_code=400, detail='Invalid voice request identifier')
    canceled = cancel_synthesis_stream(request_id)
    return GenericStatus(
        status='canceling' if canceled else 'idle',
        detail='The active voice request is stopping.' if canceled else 'No matching voice request is active.',
    )


@app.get('/api/sessions', response_model=list[SessionSummary])
def sessions():
    return list_sessions()


@app.get('/api/sessions/on-this-day', response_model=list[SessionSummary])
def sessions_on_this_day():
    return on_this_day_sessions()


@app.get('/api/sessions/gap')
def sessions_gap():
    return {'days_since_last_recording': days_since_last_recording()}


@app.get('/api/sessions/sealed', response_model=list[SessionSummary])
def sessions_sealed():
    return sealed_sessions()


@app.get('/api/sessions/{session_id}', response_model=SessionDetail)
def session_detail(session_id: str, include_transcript: bool = True):
    try:
        return get_session(session_id, include_transcript=include_transcript)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get('/api/sessions/{session_id}/related')
def session_related(session_id: str):
    try:
        return related_sessions(session_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.put('/api/sessions/{session_id}/transcript')
def update_transcript(session_id: str, payload: TranscriptUpdate):
    try:
        if is_sealed(session_id):
            raise HTTPException(status_code=403, detail='This memory is sealed until its unlock date')
        session = safe_session_dir(session_id)
        with session_lock(session_id):
            revision = revise_transcript(session, payload.transcript, payload.reason)
        return {'status': 'ok', 'session_id': session_id, 'revision_id': revision.stem}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.post('/api/sessions/{session_id}/archive')
def archive(session_id: str, confirm: bool = Query(default=False)):
    if not confirm:
        raise HTTPException(status_code=400, detail='Set confirm=true to archive this session non-destructively')
    try:
        archive_session(session_id)
        return {'status': 'archived', 'session_id': session_id}
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@app.post('/api/sessions/{session_id}/seal')
def seal_session(session_id: str, payload: SealRequest):
    if payload.unlock_at.tzinfo is None:
        unlock_at = payload.unlock_at.replace(tzinfo=timezone.utc)
    else:
        unlock_at = payload.unlock_at.astimezone(timezone.utc)
    if unlock_at <= datetime.now(timezone.utc):
        raise HTTPException(status_code=400, detail='unlock_at must be in the future')
    try:
        seal_until(safe_session_dir(session_id), unlock_at)
        return {'status': 'sealed', 'session_id': session_id, 'unlock_at': unlock_at.isoformat()}
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@app.get('/api/sessions/{session_id}/export')
def export_session(session_id: str):
    if is_sealed(session_id):
        raise HTTPException(status_code=403, detail='This memory is sealed until its unlock date')
    try:
        export_path = build_session_export(session_id)
    except (FileNotFoundError, ValueError) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return FileResponse(
        export_path,
        media_type='application/zip',
        filename=f'{session_id}.zip',
        background=BackgroundTask(export_path.unlink, missing_ok=True),
    )


@app.get('/api/reconciliation', response_model=ReconciliationReport)
def reconcile():
    return reconciliation_report()


@app.get('/api/vector/reindex-plan')
def reindex_plan():
    report = reconciliation_report()
    return {
        'source_collection': settings.chroma_collection,
        'target_collection': settings.chroma_migration_collection,
        'sessions': report.checked_sessions,
        'existing_issues': report.issue_count,
        'writes_performed': False,
    }


@app.post('/api/vector/reindex/start')
def start_reindex_job(confirm: bool = Query(default=False)):
    if not confirm:
        raise HTTPException(
            status_code=400,
            detail='Set confirm=true to build the side-by-side collection; the active collection will not change',
        )
    try:
        job = job_manager.create(mode='reindex-v2', message='Queued side-by-side vector reindex')
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    def local_reindex():
        with ollama_client.local_embedding_batch():
            reindex_to_migration_collection(job.id)
    job_manager.run_in_thread(job.id, local_reindex)
    return job


@app.post('/api/backups/structured')
def structured_backup():
    try:
        job = job_manager.create(mode='structured-backup', message='Queued full safety copy')
    except JobConflictError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

    def run_backup() -> None:
        job_manager.update(job.id, status='running', message='Preparing the safety copy')

        def progress(processed: int, total: int, message: str) -> None:
            job_manager.update(job.id, processed=processed, total=total, message=message)

        result = create_structured_backup(progress=progress)
        current_job = job_manager.get(job.id)
        job_manager.update(
            job.id,
            status='done',
            completed=True,
            processed=current_job.total if current_job else 0,
            message='Full safety copy completed',
            result=result,
        )

    job_manager.run_in_thread(job.id, run_backup)
    return job
