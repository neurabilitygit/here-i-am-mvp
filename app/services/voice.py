from __future__ import annotations

import json
import subprocess
from datetime import datetime, timezone
from pathlib import Path

import requests

from config import settings
from models.schemas import VoiceCandidate, VoicePrepareRequest, VoiceStatus
from services.storage import atomic_write_text, list_session_dirs, safe_session_dir, session_paths


STATUS_PATH = Path(settings.voice_dir) / 'voice_status.json'
REFERENCE_PATH = Path(settings.voice_dir) / 'voice_reference.wav'
REFERENCE_TEXT_PATH = Path(settings.voice_dir) / 'voice_reference.txt'


def _duration(path: Path) -> float:
    completed = subprocess.run(
        ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'json', str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    try:
        return float(json.loads(completed.stdout)['format']['duration'])
    except Exception:
        return 0


def _transcript_words(path: Path) -> int:
    if not path.exists():
        return 0
    return len(path.read_text(encoding='utf-8').split())


def list_voice_candidates(limit: int = 12) -> list[VoiceCandidate]:
    candidates = []
    for session in list_session_dirs():
        paths = session_paths(session)
        if not paths['audio'].exists() or not paths['transcript'].exists():
            continue
        duration = _duration(paths['audio'])
        words = _transcript_words(paths['transcript'])
        if duration < 20 or words < 30:
            continue
        wpm = words / (duration / 60)
        duration_fit = max(0, 1 - abs(min(duration, 900) - 300) / 600)
        pace_fit = max(0, 1 - abs(wpm - 145) / 145)
        score = round((duration_fit * 0.45 + pace_fit * 0.35 + min(words / 1200, 1) * 0.2) * 100, 1)
        candidates.append(VoiceCandidate(
            session_id=session.name,
            duration_seconds=round(duration, 1),
            transcript_words=words,
            words_per_minute=round(wpm, 1),
            score=score,
        ))
    return sorted(candidates, key=lambda item: item.score, reverse=True)[:limit]


def load_voice_status() -> VoiceStatus:
    if STATUS_PATH.exists():
        try:
            status = VoiceStatus.model_validate_json(STATUS_PATH.read_text(encoding='utf-8'))
        except Exception:
            status = VoiceStatus()
    else:
        status = VoiceStatus()
    status.reference_ready = REFERENCE_PATH.exists() and REFERENCE_TEXT_PATH.exists()
    status.cloud_voice_configured = bool(settings.elevenlabs_voice_id or getattr(status, 'voice_id', ''))
    try:
        response = requests.get(f'{settings.voice_bridge_url.rstrip("/")}/health', timeout=2)
        status.bridge_ready = response.ok
        if response.ok:
            bridge = response.json()
            status.bridge_busy = bool(bridge.get('busy'))
            status.bridge_busy_seconds = round(float(bridge.get('busy_seconds') or 0), 1)
            status.bridge_request_id = str(bridge.get('active_request_id') or '')
    except Exception:
        status.bridge_ready = False
    return status


def _save_status(status: VoiceStatus, extra: dict | None = None) -> None:
    value = status.model_dump(mode='json')
    if extra:
        value.update(extra)
    atomic_write_text(STATUS_PATH, json.dumps(value, ensure_ascii=False, indent=2))


def prepare_voice_reference(request: VoicePrepareRequest) -> VoiceStatus:
    if not request.confirm_voice_rights:
        raise ValueError('Voice rights confirmation is required')
    session = safe_session_dir(request.session_id)
    paths = session_paths(session)
    if not paths['audio'].exists() or not paths['transcript'].exists():
        raise FileNotFoundError('The selected session needs both audio and a transcript')
    source_duration = _duration(paths['audio'])
    if request.reference_start_seconds + request.reference_duration_seconds > source_duration:
        raise ValueError('The requested reference segment extends beyond the recording')
    Path(settings.voice_dir).mkdir(parents=True, exist_ok=True)
    command = [
        'ffmpeg', '-y', '-ss', str(request.reference_start_seconds), '-t', str(request.reference_duration_seconds),
        '-i', str(paths['audio']), '-ac', '1', '-ar', '24000',
        '-af', 'highpass=f=70,lowpass=f=11000,loudnorm=I=-18:TP=-2:LRA=7', str(REFERENCE_PATH),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=180)
    if completed.returncode != 0 or not REFERENCE_PATH.exists():
        raise RuntimeError('Reference audio preparation failed')
    reference_text = ''
    try:
        from services.pipeline import whisper_model
        segments, _info = whisper_model().transcribe(str(REFERENCE_PATH), vad_filter=True)
        reference_text = ' '.join(segment.text.strip() for segment in segments).strip()
    except Exception:
        # The local bridge can fall back to speaker-embedding-only cloning.
        reference_text = ''
    atomic_write_text(REFERENCE_TEXT_PATH, reference_text)
    now = datetime.now(timezone.utc)
    status = VoiceStatus(
        enabled=True,
        provider=request.provider,
        consented=True,
        consented_at=now,
        reference_ready=True,
        reference_session_id=request.session_id,
        reference_seconds=request.reference_duration_seconds,
    )
    extra = {}
    if request.provider == 'elevenlabs':
        if not settings.elevenlabs_api_key:
            raise RuntimeError('ElevenLabs is selected but ELEVENLABS_API_KEY is not configured')
        with REFERENCE_PATH.open('rb') as handle:
            response = requests.post(
                'https://api.elevenlabs.io/v1/voices/add',
                headers={'xi-api-key': settings.elevenlabs_api_key},
                data={'name': 'Here I Am - consented voice'},
                files={'files': ('voice_reference.wav', handle, 'audio/wav')},
                timeout=300,
            )
        response.raise_for_status()
        extra['voice_id'] = response.json().get('voice_id', '')
        status.cloud_voice_configured = bool(extra['voice_id'])
    _save_status(status, extra)
    return load_voice_status()


def revoke_voice(delete_reference: bool = True) -> VoiceStatus:
    status = load_voice_status()
    status.enabled = False
    status.consented = False
    status.revoked_at = datetime.now(timezone.utc)
    if delete_reference:
        REFERENCE_PATH.unlink(missing_ok=True)
        REFERENCE_TEXT_PATH.unlink(missing_ok=True)
    _save_status(status)
    return load_voice_status()


def synthesize(text: str, speed: float = 1.0, request_id: str = '') -> tuple[bytes, str, str]:
    status = load_voice_status()
    if not status.enabled or not status.consented:
        raise RuntimeError('Voice synthesis is not enabled and consented')
    raw_status = json.loads(STATUS_PATH.read_text(encoding='utf-8')) if STATUS_PATH.exists() else {}
    provider = status.provider
    if provider == 'elevenlabs':
        voice_id = raw_status.get('voice_id') or settings.elevenlabs_voice_id
        if not settings.elevenlabs_api_key or not voice_id:
            raise RuntimeError('The ElevenLabs voice is not configured')
        response = requests.post(
            f'https://api.elevenlabs.io/v1/text-to-speech/{voice_id}/stream',
            params={'output_format': 'mp3_44100_128', 'enable_logging': 'false'},
            headers={'xi-api-key': settings.elevenlabs_api_key, 'Content-Type': 'application/json'},
            json={
                'text': text,
                'model_id': settings.elevenlabs_model,
                'voice_settings': {'speed': speed, 'stability': 0.55, 'similarity_boost': 0.85},
            },
            timeout=300,
        )
        response.raise_for_status()
        return response.content, 'audio/mpeg', provider

    _release_local_chat_model()
    host_reference = str(Path(settings.voice_host_data_root) / 'appdata' / 'voice' / REFERENCE_PATH.name)
    response = requests.post(
        f'{settings.voice_bridge_url.rstrip("/")}/synthesize',
        json={
            'text': text,
            'reference_audio': host_reference,
            'reference_text': REFERENCE_TEXT_PATH.read_text(encoding='utf-8') if REFERENCE_TEXT_PATH.exists() else '',
            'speed': speed,
            'request_id': request_id,
        },
        timeout=(5, settings.voice_batch_timeout_seconds),
    )
    if response.status_code == 409:
        try:
            detail = response.json().get('detail', 'The local voice is already preparing another answer')
        except ValueError:
            detail = 'The local voice is already preparing another answer'
        raise RuntimeError(detail)
    response.raise_for_status()
    return response.content, response.headers.get('content-type', 'audio/wav'), provider


def _release_local_chat_model() -> None:
    """Free unified GPU memory before local voice synthesis.

    The next local Talk request reloads Gemma normally. Embeddinggemma is left
    resident because retrieval is still needed for every provider.
    """
    try:
        running = requests.get(
            f'{settings.ollama_base_url.rstrip("/")}/api/ps',
            timeout=2,
        )
        running.raise_for_status()
        loaded_names = {item.get('name', '').split(':')[0] for item in running.json().get('models', [])}
        if settings.ollama_chat_model.split(':')[0] not in loaded_names:
            return
        requests.post(
            f'{settings.ollama_base_url.rstrip("/")}/api/generate',
            json={'model': settings.ollama_chat_model, 'keep_alive': 0},
            timeout=8,
        )
    except requests.RequestException:
        pass


def open_synthesis_stream(text: str, speed: float = 1.0, request_id: str = '') -> tuple[requests.Response, str]:
    status = load_voice_status()
    if not status.enabled or not status.consented:
        raise RuntimeError('Voice synthesis is not enabled and consented')
    if status.provider == 'elevenlabs':
        raise RuntimeError('Streaming playback currently requires the local cloned voice')

    _release_local_chat_model()
    host_reference = str(Path(settings.voice_host_data_root) / 'appdata' / 'voice' / REFERENCE_PATH.name)
    response = requests.post(
        f'{settings.voice_bridge_url.rstrip("/")}/stream',
        json={
            'text': text,
            'reference_audio': host_reference,
            'reference_text': REFERENCE_TEXT_PATH.read_text(encoding='utf-8') if REFERENCE_TEXT_PATH.exists() else '',
            'speed': speed,
            'request_id': request_id,
        },
        stream=True,
        timeout=(5, settings.voice_request_timeout_seconds),
    )
    if response.status_code == 409:
        try:
            detail = response.json().get('detail', 'The local voice is already preparing another answer')
        except ValueError:
            detail = 'The local voice is already preparing another answer'
        response.close()
        raise RuntimeError(detail)
    response.raise_for_status()
    return response, 'local'


def cancel_synthesis_stream(request_id: str) -> bool:
    if not request_id:
        return False
    try:
        response = requests.post(
            f'{settings.voice_bridge_url.rstrip("/")}/cancel/{request_id}',
            timeout=2,
        )
        return response.ok and response.json().get('status') == 'canceling'
    except (requests.RequestException, ValueError):
        return False
