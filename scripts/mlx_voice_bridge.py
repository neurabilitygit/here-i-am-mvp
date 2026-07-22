"""Apple-Silicon-native batch Qwen3-TTS voice-cloning bridge."""
from __future__ import annotations

import io
import hashlib
import logging
import os
import re
import shutil
import threading
import time
import uuid
from pathlib import Path

import numpy as np
import soundfile as sf
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field


MODEL_ID = os.environ.get(
    'QWEN_TTS_MLX_MODEL',
    'mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16',
)
STREAMING_INTERVAL = float(os.environ.get('QWEN_TTS_STREAMING_INTERVAL', '0.8'))
SENTENCE_BATCH_SIZE = max(2, min(4, int(os.environ.get('QWEN_TTS_SENTENCE_BATCH_SIZE', '2'))))
WATCHDOG_SECONDS = max(30, min(120, int(os.environ.get('QWEN_TTS_WATCHDOG_SECONDS', '110'))))
MAX_REQUEST_SECONDS = max(
    WATCHDOG_SECONDS,
    min(840, int(os.environ.get('QWEN_TTS_MAX_REQUEST_SECONDS', '780'))),
)
CACHE_LIMIT = max(8, int(os.environ.get('QWEN_TTS_CACHE_LIMIT', '96')))
CACHE_MAX_BYTES = max(128 * 1024 * 1024, int(os.environ.get('QWEN_TTS_CACHE_MAX_BYTES', str(2 * 1024 * 1024 * 1024))))
CACHE_DIR = os.environ.get('QWEN_TTS_CACHE_DIR', '')
CACHE_SCHEMA_VERSION = 'sentence-foundry-v3-clean-boundaries'
app = FastAPI(title='Here I Am MLX voice bridge')
logger = logging.getLogger('here_i_am_voice')
LOCAL_BRIDGE_TOKEN = os.environ.get('LOCAL_BRIDGE_TOKEN', 'here-i-am-local-v1')
_model = None
_model_lock = threading.Lock()
_generation_lock = threading.Lock()
_state_lock = threading.Lock()
_active_request_id = ''
_active_started_at = 0.0
_active_first_frame_at = 0.0
_active_cancel_event: threading.Event | None = None
_active_cache_key = ''
_active_segments_total = 0
_active_segments_complete = 0
_reference_cache_signature: tuple[str, int, int] | None = None
_reference_cache_audio = None


@app.middleware('http')
async def protect_mutations(request: Request, call_next):
    if request.method != 'GET' and request.headers.get('X-Here-I-Am-Local') != LOCAL_BRIDGE_TOKEN:
        from fastapi.responses import JSONResponse

        return JSONResponse(status_code=403, content={'detail': 'Local bridge authorization is required'})
    return await call_next(request)


class SynthesisRequest(BaseModel):
    text: str = Field(min_length=1, max_length=12000)
    reference_audio: str
    reference_text: str = ''
    speed: float = Field(default=1.0, ge=0.7, le=1.3)
    request_id: str = Field(default='', max_length=80, pattern=r'^[A-Za-z0-9_-]*$')


@app.post('/auth/check')
def auth_check():
    return {'status': 'ok'}


def load_model():
    global _model
    with _model_lock:
        if _model is None:
            from mlx_audio.tts.utils import load_model as mlx_load_model

            _model = mlx_load_model(MODEL_ID)
        return _model


def wav_bytes(audio, sample_rate: int) -> bytes:
    buffer = io.BytesIO()
    sf.write(buffer, np.asarray(audio, dtype=np.float32), sample_rate, format='WAV')
    return buffer.getvalue()


def sentence_segments(text: str, minimum_words: int = 15, maximum_words: int = 30) -> list[str]:
    """Create natural, bounded speech units without losing the original words."""
    sentences = [value.strip() for value in re.split(r'(?<=[.!?])\s+', text.strip()) if value.strip()]
    pieces: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        while len(words) > maximum_words:
            split_at = maximum_words
            for index in range(maximum_words - 1, minimum_words - 1, -1):
                if words[index - 1].endswith((',', ';', ':', '—')):
                    split_at = index
                    break
            pieces.append(' '.join(words[:split_at]))
            words = words[split_at:]
        if words:
            pieces.append(' '.join(words))

    segments: list[str] = []
    for piece in pieces:
        piece_words = piece.split()
        previous_words = segments[-1].split() if segments else []
        if segments and len(piece_words) < minimum_words and len(previous_words) + len(piece_words) <= maximum_words:
            segments[-1] = f'{segments[-1]} {piece}'
        elif segments and len(piece_words) < minimum_words:
            needed = minimum_words - len(piece_words)
            if len(previous_words) - needed >= minimum_words:
                segments[-1] = ' '.join(previous_words[:-needed])
                segments.append(' '.join(previous_words[-needed:] + piece_words))
            else:
                segments.append(piece)
        else:
            segments.append(piece)
    return segments or [text.strip()]


def adaptive_token_ceiling(text: str) -> int:
    return max(90, min(480, len(text.split()) * 8))


def watchdog_failure(started: float, last_progress: float, now: float) -> str:
    if now - started > MAX_REQUEST_SECONDS:
        return 'Voice preparation exceeded the absolute local safety limit'
    if now - last_progress > WATCHDOG_SECONDS:
        return 'Voice preparation stopped making audio progress'
    return ''


def trim_segment_artifacts(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    """Remove generator lead-in/tail noise and soften the retained speech edges."""
    value = np.asarray(audio, dtype=np.float32).reshape(-1)
    if not value.size:
        return value
    frame_size = max(1, int(sample_rate * 0.01))
    frame_count = int(np.ceil(value.size / frame_size))
    rms = np.empty(frame_count, dtype=np.float32)
    for index in range(frame_count):
        frame = value[index * frame_size:(index + 1) * frame_size]
        rms[index] = float(np.sqrt(np.mean(np.square(frame)))) if frame.size else 0.0
    peak_rms = float(np.max(rms))
    if peak_rms <= 1e-6:
        return np.zeros(0, dtype=np.float32)
    noise_floor = float(np.percentile(rms, 20))
    threshold = max(0.0025, min(0.02, noise_floor * 3.0), peak_rms * 0.025)
    active = np.flatnonzero(rms >= threshold)
    if active.size:
        padding = int(sample_rate * 0.035)
        start = max(0, int(active[0]) * frame_size - padding)
        end = min(value.size, (int(active[-1]) + 1) * frame_size + padding)
        value = value[start:end].copy()
    else:
        value = value.copy()
    fade_size = min(max(1, int(sample_rate * 0.022)), value.size // 2)
    if fade_size:
        phase = np.linspace(0.0, np.pi / 2.0, fade_size, dtype=np.float32)
        fade = np.square(np.sin(phase))
        value[:fade_size] *= fade
        value[-fade_size:] *= fade[::-1]
    return value


def stitch_audio(segments: list[np.ndarray], sample_rate: int, speed: float = 1.0) -> np.ndarray:
    # Faded speech-to-silence joins avoid the hard discontinuities that sound
    # like clicks or extra consonants while retaining a natural sentence pause.
    pause = np.zeros(max(1, int(sample_rate * 0.075)), dtype=np.float32)
    values: list[np.ndarray] = []
    for index, audio in enumerate(segments):
        if index:
            values.append(pause)
        values.append(np.asarray(audio, dtype=np.float32).reshape(-1))
    combined = np.concatenate(values) if values else np.zeros(0, dtype=np.float32)
    if combined.size and abs(speed - 1.0) > 0.01:
        new_size = max(1, int(combined.size / speed))
        combined = np.interp(
            np.linspace(0, combined.size - 1, new_size),
            np.arange(combined.size),
            combined,
        ).astype(np.float32)
    return combined


def cache_key(request: SynthesisRequest) -> str:
    reference = Path(request.reference_audio)
    stat = reference.stat()
    material = '\n'.join((
        CACHE_SCHEMA_VERSION,
        MODEL_ID,
        request.text.strip(),
        request.reference_text.strip(),
        f'{request.speed:.3f}',
        str(reference.resolve()),
        str(stat.st_size),
        str(stat.st_mtime_ns),
    ))
    return hashlib.sha256(material.encode('utf-8')).hexdigest()


def cache_root(request: SynthesisRequest) -> Path:
    root = Path(CACHE_DIR or str(Path(request.reference_audio).parent / 'cache'))
    root.mkdir(parents=True, exist_ok=True)
    return root


def cache_path(request: SynthesisRequest, key: str) -> Path:
    return cache_root(request) / f'{key}.wav'


def segment_cache_dir(request: SynthesisRequest, key: str) -> Path:
    return cache_root(request) / 'segments' / key


def segment_cache_path(directory: Path, index: int) -> Path:
    return directory / f'{index:04d}.wav'


def atomic_write_bytes(destination: Path, payload: bytes) -> None:
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(f'.{destination.name}.{uuid.uuid4().hex}.tmp')
    temporary.write_bytes(payload)
    os.replace(temporary, destination)


def write_cached_segment(directory: Path, index: int, audio: np.ndarray, sample_rate: int) -> None:
    atomic_write_bytes(segment_cache_path(directory, index), wav_bytes(audio, sample_rate))
    directory.touch()


def read_cached_segment(directory: Path, index: int, expected_sample_rate: int) -> np.ndarray | None:
    path = segment_cache_path(directory, index)
    if not path.exists() or path.stat().st_size <= 44:
        return None
    try:
        audio, sample_rate = sf.read(path, dtype='float32', always_2d=False)
        value = np.asarray(audio, dtype=np.float32)
        if value.ndim > 1:
            value = value.mean(axis=1)
        value = value.reshape(-1)
        if sample_rate != expected_sample_rate or not value.size or not np.isfinite(value).all():
            raise ValueError('invalid cached segment')
        path.touch()
        directory.touch()
        return value
    except Exception:
        path.unlink(missing_ok=True)
        return None


def trim_cache(root: Path) -> None:
    entries = sorted(root.glob('*.wav'), key=lambda value: value.stat().st_mtime, reverse=True)
    for stale in entries[CACHE_LIMIT:]:
        stale.unlink(missing_ok=True)
    segment_root = root / 'segments'
    if segment_root.exists():
        directories = sorted(
            (value for value in segment_root.iterdir() if value.is_dir()),
            key=lambda value: value.stat().st_mtime,
            reverse=True,
        )
        for stale in directories[CACHE_LIMIT:]:
            shutil.rmtree(stale, ignore_errors=True)
    retained = sorted(
        (path for path in root.rglob('*') if path.is_file()),
        key=lambda value: value.stat().st_mtime,
        reverse=True,
    )
    total = 0
    for path in retained:
        try:
            size = path.stat().st_size
        except OSError:
            continue
        total += size
        if total > CACHE_MAX_BYTES:
            path.unlink(missing_ok=True)
    if segment_root.exists():
        for directory in sorted(segment_root.iterdir(), reverse=True):
            if directory.is_dir() and not any(directory.iterdir()):
                directory.rmdir()


def cached_reference_audio(path: str, expected_sample_rate: int):
    global _reference_cache_signature, _reference_cache_audio
    reference = Path(path)
    stat = reference.stat()
    signature = (str(reference.resolve()), stat.st_size, stat.st_mtime_ns)
    if signature == _reference_cache_signature and _reference_cache_audio is not None:
        return _reference_cache_audio
    audio, sample_rate = sf.read(reference, dtype='float32', always_2d=False)
    audio = np.asarray(audio, dtype=np.float32)
    if audio.ndim > 1:
        audio = audio.mean(axis=1)
    if sample_rate != expected_sample_rate:
        new_size = max(1, int(audio.size * expected_sample_rate / sample_rate))
        audio = np.interp(np.linspace(0, audio.size - 1, new_size), np.arange(audio.size), audio).astype(np.float32)
    import mlx.core as mx
    _reference_cache_audio = mx.array(audio)
    _reference_cache_signature = signature
    return _reference_cache_audio


def speech_units(text: str, limit: int = 48) -> list[str]:
    """Keep first-audio latency bounded and provide cancellation boundaries."""
    sentences = re.split(r'(?<=[.!?])\s+', text.strip())
    units: list[str] = []
    for sentence in sentences:
        words = sentence.split()
        current: list[str] = []
        for word in words:
            if current and len(' '.join(current + [word])) > limit:
                units.append(' '.join(current))
                current = []
            current.append(word)
        if current:
            units.append(' '.join(current))
    return units


def begin_generation(request_id: str, key: str, segments_total: int) -> tuple[str, threading.Event] | None:
    global _active_request_id, _active_started_at, _active_first_frame_at, _active_cancel_event
    global _active_cache_key, _active_segments_total, _active_segments_complete
    if not _generation_lock.acquire(blocking=False):
        return None
    identifier = request_id or uuid.uuid4().hex
    cancel_event = threading.Event()
    with _state_lock:
        _active_request_id = identifier
        _active_started_at = time.monotonic()
        _active_first_frame_at = 0.0
        _active_cancel_event = cancel_event
        _active_cache_key = key
        _active_segments_total = segments_total
        _active_segments_complete = 0
    return identifier, cancel_event


def mark_first_frame(request_id: str) -> None:
    global _active_first_frame_at
    with _state_lock:
        if _active_request_id == request_id and not _active_first_frame_at:
            _active_first_frame_at = time.monotonic()


def mark_segments_complete(request_id: str, count: int) -> None:
    global _active_segments_complete
    with _state_lock:
        if _active_request_id == request_id:
            _active_segments_complete = count


def finish_generation(request_id: str) -> None:
    global _active_request_id, _active_started_at, _active_first_frame_at, _active_cancel_event
    global _active_cache_key, _active_segments_total, _active_segments_complete
    should_release = False
    with _state_lock:
        if _active_request_id == request_id:
            _active_request_id = ''
            _active_started_at = 0.0
            _active_first_frame_at = 0.0
            _active_cancel_event = None
            _active_cache_key = ''
            _active_segments_total = 0
            _active_segments_complete = 0
            should_release = True
    if should_release:
        _generation_lock.release()


@app.get('/health')
def health():
    with _state_lock:
        request_id = _active_request_id
        started_at = _active_started_at
        first_frame_at = _active_first_frame_at
        active_cache_key = _active_cache_key
        segments_total = _active_segments_total
        segments_complete = _active_segments_complete
    return {
        'status': 'ok',
        'engine': 'qwen3-tts-mlx',
        'model': MODEL_ID,
        'model_loaded': _model is not None,
        'device': 'mlx',
        'streaming': True,
        'batch_wav': True,
        'busy': bool(request_id),
        'busy_seconds': round(time.monotonic() - started_at, 1) if started_at else 0,
        'active_request_id': request_id,
        'first_frame_ready': bool(first_frame_at),
        'watchdog_seconds': WATCHDOG_SECONDS,
        'watchdog_mode': 'no_progress',
        'max_request_seconds': MAX_REQUEST_SECONDS,
        'sentence_batch_size': SENTENCE_BATCH_SIZE,
        'cache_max_bytes': CACHE_MAX_BYTES,
        'active_cache_key': active_cache_key,
        'segments_total': segments_total,
        'segments_complete': segments_complete,
    }


@app.post('/cancel/{request_id}')
def cancel(request_id: str):
    with _state_lock:
        if _active_request_id != request_id or _active_cancel_event is None:
            return {'status': 'idle', 'request_id': request_id}
        _active_cancel_event.set()
    return {'status': 'canceling', 'request_id': request_id}


@app.post('/warm')
def warm():
    try:
        load_model()
        return {'status': 'ready', 'model': MODEL_ID}
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@app.post('/cache/clear')
def clear_cache():
    if not _generation_lock.acquire(blocking=False):
        raise HTTPException(status_code=409, detail='Voice cache cannot be cleared while speech is being prepared')
    try:
        if not CACHE_DIR:
            raise HTTPException(status_code=409, detail='Voice cache location is not configured')
        root = Path(CACHE_DIR)
        shutil.rmtree(root, ignore_errors=True)
        root.mkdir(parents=True, exist_ok=True)
        return {'status': 'cleared'}
    finally:
        _generation_lock.release()


def validate_reference(request: SynthesisRequest) -> None:
    if not Path(request.reference_audio).exists():
        raise HTTPException(status_code=404, detail='Reference audio was not found on the host')


@app.post('/synthesize')
def synthesize(request: SynthesisRequest):
    validate_reference(request)
    key = cache_key(request)
    destination = cache_path(request, key)
    trim_cache(destination.parent)
    if destination.exists() and destination.stat().st_size > 44:
        destination.touch()
        return Response(
            destination.read_bytes(), media_type='audio/wav',
            headers={'X-Voice-Engine':'qwen3-tts-mlx','X-Voice-Cache':'hit','X-Voice-Cache-Key':key},
        )
    segments = sentence_segments(request.text)
    generation = begin_generation(request.request_id, key, len(segments))
    if generation is None:
        raise HTTPException(status_code=409, detail='The local voice is already preparing another answer')
    request_id, cancel_event = generation
    segment_directory = segment_cache_dir(request, key)
    timeout_marker = segment_directory / '.retry-single'
    try:
        model = load_model()
        reference_audio = cached_reference_audio(request.reference_audio, int(model.sample_rate))
        sample_rate = int(model.sample_rate)
        segment_directory.mkdir(parents=True, exist_ok=True)
        completed_audio: list[np.ndarray | None] = [
            read_cached_segment(segment_directory, index, sample_rate)
            for index in range(len(segments))
        ]
        resumed_segments = sum(value is not None for value in completed_audio)
        mark_segments_complete(request_id, resumed_segments)
        missing_indexes = [index for index, value in enumerate(completed_audio) if value is None]
        effective_batch_size = 1 if timeout_marker.exists() else SENTENCE_BATCH_SIZE
        started = time.monotonic()
        last_progress = started
        logger.info(
            'voice synthesis started request_id=%s segments_total=%s segments_resumed=%s batch_size=%s',
            request_id, len(segments), resumed_segments, effective_batch_size,
        )
        for missing_start in range(0, len(missing_indexes), effective_batch_size):
            group_indexes = missing_indexes[missing_start:missing_start + effective_batch_size]
            group = [segments[index] for index in group_indexes]
            group_parts: list[list[np.ndarray]] = [[] for _ in group]
            maximum_tokens = max(adaptive_token_ceiling(value) for value in group)
            for result in model.batch_generate(
                texts=group,
                ref_audio=reference_audio,
                ref_text=request.reference_text,
                lang_code='English',
                max_tokens=maximum_tokens,
                stream=True,
                streaming_interval=STREAMING_INTERVAL,
                verbose=False,
            ):
                if cancel_event.is_set():
                    raise HTTPException(status_code=409, detail='Voice preparation was canceled')
                now = time.monotonic()
                if failure := watchdog_failure(started, last_progress, now):
                    raise HTTPException(status_code=504, detail=failure)
                last_progress = now
                mark_first_frame(request_id)
                sample_rate = int(result.sample_rate)
                group_parts[int(result.sequence_idx)].append(np.asarray(result.audio, dtype=np.float32).reshape(-1))
            for index, values in enumerate(group_parts):
                if not values:
                    raise HTTPException(status_code=503, detail=f'The local voice produced no audio for segment {group_indexes[index] + 1}')
                segment_index = group_indexes[index]
                segment_audio = trim_segment_artifacts(np.concatenate(values), sample_rate)
                if not segment_audio.size:
                    raise HTTPException(status_code=503, detail=f'The local voice produced only silence for segment {segment_index + 1}')
                write_cached_segment(segment_directory, segment_index, segment_audio, sample_rate)
                completed_audio[segment_index] = segment_audio
                completed_count = sum(value is not None for value in completed_audio)
                mark_segments_complete(request_id, completed_count)
                logger.info(
                    'voice segment completed request_id=%s segment=%s segments_complete=%s segments_total=%s elapsed=%.1f',
                    request_id, segment_index + 1, completed_count, len(segments), time.monotonic() - started,
                )
        if any(value is None for value in completed_audio):
            raise HTTPException(status_code=503, detail='The local voice did not complete every speech segment')
        audio_parts = [value for value in completed_audio if value is not None]
        if not audio_parts:
            raise HTTPException(status_code=503, detail='The local voice produced no audio')
        combined = stitch_audio(audio_parts, sample_rate, request.speed)
        payload = wav_bytes(combined, sample_rate)
        atomic_write_bytes(destination, payload)
        timeout_marker.unlink(missing_ok=True)
        trim_cache(destination.parent)
        logger.info(
            'voice synthesis completed request_id=%s segments_total=%s segments_resumed=%s elapsed=%.1f bytes=%s',
            request_id, len(segments), resumed_segments, time.monotonic() - started, len(payload),
        )
        return Response(
            payload,
            media_type='audio/wav',
            headers={
                'X-Voice-Engine': 'qwen3-tts-mlx',
                'X-Voice-Request-ID': request_id,
                'X-Voice-Cache': 'miss',
                'X-Voice-Cache-Key': key,
                'X-Voice-Segments': str(len(segments)),
                'X-Voice-Segments-Resumed': str(resumed_segments),
                'X-Voice-Segment-Cache': 'hit' if resumed_segments else 'miss',
                'X-Voice-Batch-Size': str(effective_batch_size),
            },
        )
    except HTTPException as exc:
        if exc.status_code == 504:
            atomic_write_bytes(timeout_marker, b'retry incomplete segments one at a time\n')
        logger.warning(
            'voice synthesis stopped request_id=%s status=%s detail=%s',
            request_id, exc.status_code, exc.detail,
        )
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=f'Local voice generation failed: {exc}') from exc
    finally:
        finish_generation(request_id)
