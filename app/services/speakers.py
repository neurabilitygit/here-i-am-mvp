from __future__ import annotations

import base64
import fcntl
import json
import re
import subprocess
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterator

import requests
from slugify import slugify

from config import settings
from models.schemas import SpeakerCreate, SpeakerProfile
from services.preferences import cloud_api_key
from services.storage import atomic_write_text, load_json, save_json, session_lock, session_paths, update_processing_state


REGISTRY_VERSION = 1
SUPPORTED_REFERENCE_SECONDS = (2.0, 10.0)


class SpeakerWorkflowError(RuntimeError):
    pass


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _registry_path() -> Path:
    return Path(settings.speakers_dir) / 'registry.json'


@contextmanager
def _registry_lock() -> Iterator[None]:
    lock_path = Path(settings.locks_dir) / 'speaker-registry.lock'
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    with lock_path.open('a+', encoding='utf-8') as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def _load_registry() -> dict[str, Any]:
    path = _registry_path()
    if not path.exists():
        return {'schema_version': REGISTRY_VERSION, 'speakers': []}
    try:
        registry = load_json(path)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        raise SpeakerWorkflowError('The speaker registry cannot be read safely') from exc
    if not isinstance(registry.get('speakers'), list):
        raise SpeakerWorkflowError('The speaker registry has an invalid format')
    registry['schema_version'] = REGISTRY_VERSION
    return registry


def _save_registry(registry: dict[str, Any]) -> None:
    registry['schema_version'] = REGISTRY_VERSION
    save_json(_registry_path(), registry)


def _public_profile(record: dict[str, Any]) -> SpeakerProfile:
    avatar_id = record.get('active_avatar_id')
    avatar_url = f"/api/speakers/{record['speaker_id']}/avatar" if avatar_id else None
    reference = record.get('voice_reference_path')
    return SpeakerProfile(
        speaker_id=record['speaker_id'],
        display_name=record['display_name'],
        default_role=record.get('default_role', 'other'),
        avatar_url=avatar_url,
        voice_reference_ready=bool(reference and Path(reference).exists()),
        source_photo_ready=any(
            item.get('photo_id') == record.get('active_source_photo_id') and Path(item.get('path', '')).exists()
            for item in record.get('source_photos', [])
        ),
        created_at=record['created_at'],
        updated_at=record['updated_at'],
    )


def list_speakers() -> list[SpeakerProfile]:
    with _registry_lock():
        registry = _load_registry()
    return [_public_profile(record) for record in registry['speakers']]


def get_speaker_record(speaker_id: str) -> dict[str, Any]:
    safe_speaker_id(speaker_id)
    with _registry_lock():
        registry = _load_registry()
        record = next((item for item in registry['speakers'] if item.get('speaker_id') == speaker_id), None)
    if record is None:
        raise KeyError('Speaker does not exist')
    return record


def update_speaker_record(speaker_id: str, **updates: Any) -> dict[str, Any]:
    safe_speaker_id(speaker_id)
    with _registry_lock():
        registry = _load_registry()
        record = next((item for item in registry['speakers'] if item.get('speaker_id') == speaker_id), None)
        if record is None:
            raise KeyError('Speaker does not exist')
        record.update(updates)
        record['updated_at'] = _now()
        _save_registry(registry)
        return dict(record)


def create_speaker(payload: SpeakerCreate) -> SpeakerProfile:
    display_name = ' '.join(payload.display_name.split())
    stem = slugify(display_name)[:48] or 'speaker'
    created_at = _now()
    with _registry_lock():
        registry = _load_registry()
        existing_ids = {record.get('speaker_id') for record in registry['speakers']}
        speaker_id = stem
        if speaker_id in existing_ids:
            speaker_id = f'{stem}-{uuid.uuid4().hex[:6]}'
        record = {
            'speaker_id': speaker_id,
            'display_name': display_name,
            'default_role': payload.default_role,
            'voice_reference_path': None,
            'active_avatar_id': None,
            'avatars': [],
            'source_photos': [],
            'created_at': created_at,
            'updated_at': created_at,
        }
        registry['speakers'].append(record)
        _save_registry(registry)
    (Path(settings.speakers_dir) / speaker_id).mkdir(parents=True, exist_ok=True)
    return _public_profile(record)


def safe_speaker_id(speaker_id: str) -> str:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', speaker_id):
        raise ValueError('Invalid speaker id')
    return speaker_id


def _known_speaker_references() -> list[tuple[str, str]]:
    references: list[tuple[str, str]] = []
    for profile in list_speakers():
        if len(references) == 4:
            break
        record = get_speaker_record(profile.speaker_id)
        path_value = record.get('voice_reference_path')
        if not path_value:
            continue
        path = Path(path_value)
        if not path.exists() or path.stat().st_size <= 0:
            continue
        encoded = base64.b64encode(path.read_bytes()).decode('ascii')
        references.append((profile.speaker_id, f'data:audio/wav;base64,{encoded}'))
    return references


def _make_diarization_input(audio_path: Path, output_path: Path) -> Path:
    if output_path.exists() and 0 < output_path.stat().st_size <= 24 * 1024 * 1024:
        return output_path
    command = [
        'ffmpeg', '-hide_banner', '-nostats', '-y', '-i', str(audio_path), '-vn', '-ac', '1', '-ar', '16000',
        '-c:a', 'libopus', '-b:a', '12k', str(output_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=900)
    if completed.returncode != 0 or not output_path.exists():
        raise SpeakerWorkflowError('The conversation audio could not be prepared for speaker recognition')
    if output_path.stat().st_size > 24 * 1024 * 1024:
        output_path.unlink(missing_ok=True)
        raise SpeakerWorkflowError('This conversation is too long for one speaker-recognition pass; split it into smaller recordings')
    return output_path


def _normalize_segments(payload: dict[str, Any]) -> list[dict[str, Any]]:
    raw_segments = payload.get('segments') or []
    if not isinstance(raw_segments, list):
        raise SpeakerWorkflowError('The speaker-recognition response did not contain usable segments')
    normalized: list[dict[str, Any]] = []
    unknown_map: dict[str, str] = {}
    for item in raw_segments:
        if not isinstance(item, dict):
            continue
        text = ' '.join(str(item.get('text') or '').split())
        if not text:
            continue
        raw_label = str(item.get('speaker') or item.get('speaker_id') or 'unknown').strip()
        if re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', raw_label):
            label = raw_label
        else:
            label = unknown_map.setdefault(raw_label, f'unknown-{len(unknown_map) + 1}')
        try:
            start = max(0.0, float(item.get('start', 0)))
            end = max(start, float(item.get('end', start)))
        except (TypeError, ValueError):
            continue
        segment = {'cluster_id': label, 'start': round(start, 3), 'end': round(end, 3), 'text': text}
        if normalized and normalized[-1]['cluster_id'] == label and start - normalized[-1]['end'] <= 1.2:
            normalized[-1]['end'] = segment['end']
            normalized[-1]['text'] = f"{normalized[-1]['text']} {text}"
        else:
            normalized.append(segment)
    if not normalized:
        raise SpeakerWorkflowError('No speech was found in the conversation recording')
    return normalized


def _transcript_text(turns: list[dict[str, Any]], names: dict[str, str] | None = None) -> str:
    names = names or {}
    return '\n\n'.join(f"**{names.get(turn['cluster_id'], turn['cluster_id'])}:** {turn['text']}" for turn in turns) + '\n'


def _auto_assign_known_speakers(session_path: Path, turns: list[dict[str, Any]]) -> bool:
    profiles = {profile.speaker_id: profile for profile in list_speakers()}
    cluster_ids = sorted({turn['cluster_id'] for turn in turns})
    if not cluster_ids or any(cluster_id not in profiles for cluster_id in cluster_ids):
        return False
    subject_count = sum(profiles[cluster_id].default_role == 'memory_subject' for cluster_id in cluster_ids)
    if subject_count != 1:
        return False
    assignments = [
        {
            'cluster_id': cluster_id,
            'speaker_id': cluster_id,
            'display_name': profiles[cluster_id].display_name,
            'role': profiles[cluster_id].default_role,
        }
        for cluster_id in cluster_ids
    ]
    apply_speaker_assignments(session_path, assignments)
    return True


def diarize_conversation(session_path: Path) -> dict[str, Any]:
    paths = session_paths(session_path)
    if not paths['audio'].exists():
        raise SpeakerWorkflowError('The recording audio is missing')
    if settings.speaker_diarization_provider == 'disabled':
        raise SpeakerWorkflowError('Conversation speaker recognition is not configured')
    api_key, _ = cloud_api_key()
    if not api_key:
        raise SpeakerWorkflowError('OpenAI speaker recognition is not configured')

    cached_result: dict[str, Any] | None = None
    cached_turns: list[dict[str, Any]] = []
    with session_lock(session_path.name):
        if paths['diarization'].exists() and paths['transcript_turns'].exists():
            cached = load_json(paths['diarization'])
            turns = load_json(paths['transcript_turns']).get('turns', [])
            if turns:
                update_processing_state(
                    session_path,
                    transcribed=True,
                    transcription_status='complete',
                    speaker_processing_status='complete',
                    speaker_review_status='needs_review',
                    speaker_count=len({turn['cluster_id'] for turn in turns}),
                )
                cached_result = cached
                cached_turns = turns
        if cached_result is None:
            update_processing_state(
                session_path,
                speaker_processing_status='running',
                speaker_review_status='pending',
                transcription_status='running',
            )
    if cached_result is not None:
        cached_result['auto_assigned'] = _auto_assign_known_speakers(session_path, cached_turns)
        return cached_result

    try:
        input_path = _make_diarization_input(paths['audio'], session_path / 'diarization-input.webm')
        references = _known_speaker_references()
        data: list[tuple[str, str]] = [
            ('model', settings.speaker_diarization_model),
            ('response_format', 'diarized_json'),
            ('chunking_strategy', 'auto'),
        ]
        for name, reference in references:
            data.append(('known_speaker_names[]', name))
            data.append(('known_speaker_references[]', reference))
        with input_path.open('rb') as audio_handle:
            response = requests.post(
                f"{settings.openai_base_url.rstrip('/')}/audio/transcriptions",
                headers={'Authorization': f'Bearer {api_key}'},
                data=data,
                files={'file': (input_path.name, audio_handle, 'audio/webm')},
                timeout=(settings.provider_connect_timeout_seconds, settings.speaker_diarization_timeout_seconds),
            )
        response.raise_for_status()
        payload = response.json()
        turns = _normalize_segments(payload)
        result = {
            'schema_version': 1,
            'provider': 'openai',
            'model': settings.speaker_diarization_model,
            'created_at': _now(),
            'known_speakers_supplied': [name for name, _ in references],
            'turns': turns,
        }
        with session_lock(session_path.name):
            save_json(paths['diarization'], result)
            save_json(paths['transcript_turns'], {'schema_version': 1, 'turns': turns})
            atomic_write_text(paths['transcript'], _transcript_text(turns))
            update_processing_state(
                session_path,
                transcribed=True,
                transcription_status='complete',
                speaker_processing_status='complete',
                speaker_review_status='needs_review',
                speaker_count=len({turn['cluster_id'] for turn in turns}),
            )
        auto_assigned = _auto_assign_known_speakers(session_path, turns)
        result['auto_assigned'] = auto_assigned
        return result
    except Exception:
        update_processing_state(
            session_path,
            speaker_processing_status='error',
            speaker_review_status='blocked',
            transcription_status='error',
        )
        raise


def speaker_review(session_path: Path) -> dict[str, Any]:
    paths = session_paths(session_path)
    if not paths['transcript_turns'].exists():
        raise FileNotFoundError('Speaker recognition has not finished for this recording')
    turns = load_json(paths['transcript_turns']).get('turns', [])
    assignments_by_cluster: dict[str, Any] = {}
    if paths['speaker_assignments'].exists():
        assignments_by_cluster = {
            assignment['cluster_id']: assignment
            for assignment in load_json(paths['speaker_assignments']).get('assignments', [])
        }
    clusters: list[dict[str, Any]] = []
    for cluster_id in sorted({turn['cluster_id'] for turn in turns}):
        cluster_turns = [turn for turn in turns if turn['cluster_id'] == cluster_id]
        duration = sum(max(0.0, turn['end'] - turn['start']) for turn in cluster_turns)
        preview = ' '.join(turn['text'] for turn in cluster_turns)[:600]
        clusters.append(
            {
                'cluster_id': cluster_id,
                'duration_seconds': round(duration, 1),
                'turn_count': len(cluster_turns),
                'preview': preview,
                'sample_url': f'/api/sessions/{session_path.name}/speaker-samples/{cluster_id}',
                'assignment': assignments_by_cluster.get(cluster_id),
            }
        )
    state = load_json(paths['state'])
    return {
        'session_id': session_path.name,
        'status': state.get('speaker_review_status', 'needs_review'),
        'clusters': clusters,
        'speakers': [profile.model_dump(mode='json') for profile in list_speakers()],
    }


def _extract_reference(session_path: Path, speaker_id: str, cluster_turns: list[dict[str, Any]]) -> str | None:
    eligible = [turn for turn in cluster_turns if turn['end'] - turn['start'] >= SUPPORTED_REFERENCE_SECONDS[0]]
    if not eligible:
        return None
    best = max(eligible, key=lambda turn: turn['end'] - turn['start'])
    duration = min(float(settings.speaker_reference_seconds), SUPPORTED_REFERENCE_SECONDS[1], best['end'] - best['start'])
    speaker_dir = Path(settings.speakers_dir) / speaker_id
    speaker_dir.mkdir(parents=True, exist_ok=True)
    reference_path = speaker_dir / 'voice-reference.wav'
    command = [
        'ffmpeg', '-hide_banner', '-nostats', '-y', '-ss', str(best['start']), '-t', str(duration),
        '-i', str(session_paths(session_path)['audio']), '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(reference_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if completed.returncode != 0 or not reference_path.exists():
        return None
    return str(reference_path)


def _build_memory_units(turns: list[dict[str, Any]], assignments: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    units: list[dict[str, Any]] = []
    context_buffer: list[dict[str, Any]] = []
    for turn in turns:
        assignment = assignments[turn['cluster_id']]
        if assignment['role'] == 'memory_subject':
            context = [item for item in context_buffer if assignments[item['cluster_id']]['role'] == 'interviewer'][-2:]
            units.append(
                {
                    'memory_unit_id': f"unit-{len(units) + 1:04d}",
                    'subject_speaker_id': assignment['speaker_id'],
                    'subject_display_name': assignment['display_name'],
                    'subject_evidence': turn['text'],
                    'retrieval_context': ' '.join(item['text'] for item in context),
                    'interviewer_speaker_ids': list(
                        dict.fromkeys(assignments[item['cluster_id']]['speaker_id'] for item in context)
                    ),
                    'start': turn['start'],
                    'end': turn['end'],
                }
            )
            context_buffer = []
        else:
            context_buffer.append(turn)
            context_buffer = context_buffer[-4:]
    return units


def apply_speaker_assignments(session_path: Path, assignments_payload: list[dict[str, Any]]) -> dict[str, Any]:
    paths = session_paths(session_path)
    if not paths['transcript_turns'].exists():
        raise SpeakerWorkflowError('Speaker recognition must finish before voices can be assigned')
    turns = load_json(paths['transcript_turns']).get('turns', [])
    cluster_ids = {turn['cluster_id'] for turn in turns}
    supplied_cluster_ids = [item['cluster_id'] for item in assignments_payload]
    if len(supplied_cluster_ids) != len(cluster_ids) or set(supplied_cluster_ids) != cluster_ids:
        raise SpeakerWorkflowError('Every detected voice must be assigned exactly once')
    if sum(item.get('role') == 'memory_subject' for item in assignments_payload) != 1:
        raise SpeakerWorkflowError('Choose exactly one memory subject for this conversation')
    known_records: dict[str, dict[str, Any]] = {}
    for item in assignments_payload:
        speaker_id = item.get('speaker_id')
        if speaker_id:
            known_records[speaker_id] = get_speaker_record(speaker_id)
        elif not ' '.join(str(item.get('display_name') or '').split()):
            raise SpeakerWorkflowError('A name is required for every new voice')

    resolved: dict[str, dict[str, Any]] = {}
    for item in assignments_payload:
        speaker_id = item.get('speaker_id')
        if speaker_id:
            record = known_records[speaker_id]
            display_name = record['display_name']
        else:
            display_name = ' '.join(str(item.get('display_name') or '').split())
            if not display_name:
                raise SpeakerWorkflowError('A name is required for every new voice')
            profile = create_speaker(SpeakerCreate(display_name=display_name, default_role=item['role']))
            speaker_id = profile.speaker_id
        resolved[item['cluster_id']] = {
            'cluster_id': item['cluster_id'],
            'speaker_id': speaker_id,
            'display_name': display_name,
            'role': item['role'],
        }
    roles_by_speaker: dict[str, set[str]] = {}
    for item in resolved.values():
        roles_by_speaker.setdefault(item['speaker_id'], set()).add(item['role'])
    if any(len(roles) > 1 for roles in roles_by_speaker.values()):
        raise SpeakerWorkflowError('The same person cannot have two different roles in one conversation')
    unique_subjects = {item['speaker_id'] for item in resolved.values() if item['role'] == 'memory_subject'}

    units = _build_memory_units(turns, resolved)
    if not units:
        raise SpeakerWorkflowError('The memory subject has no spoken words in this recording')
    names = {cluster_id: item['display_name'] for cluster_id, item in resolved.items()}
    saved_assignments = {
        'schema_version': 1,
        'updated_at': _now(),
        'assignments': list(resolved.values()),
    }
    memory_units_text = ''.join(json.dumps(unit, ensure_ascii=False) + '\n' for unit in units)

    with session_lock(session_path.name):
        save_json(paths['speaker_assignments'], saved_assignments)
        atomic_write_text(paths['memory_units'], memory_units_text)
        atomic_write_text(paths['transcript'], _transcript_text(turns, names))
        update_processing_state(
            session_path,
            transcribed=True,
            analyzed=False,
            embedded=False,
            analysis_status='pending',
            embedding_status='pending',
            speaker_review_status='complete',
            speaker_count=len(resolved),
            subject_speaker_id=next(iter(unique_subjects)),
        )

    for cluster_id, assignment in resolved.items():
        record = get_speaker_record(assignment['speaker_id'])
        if record.get('default_role') == 'other':
            record = update_speaker_record(assignment['speaker_id'], default_role=assignment['role'])
        if record.get('voice_reference_path') and Path(record['voice_reference_path']).exists():
            continue
        reference = _extract_reference(
            session_path,
            assignment['speaker_id'],
            [turn for turn in turns if turn['cluster_id'] == cluster_id],
        )
        if reference:
            update_speaker_record(assignment['speaker_id'], voice_reference_path=reference)
    return {
        'session_id': session_path.name,
        'status': 'complete',
        'subject_speaker_id': next(iter(unique_subjects)),
        'memory_unit_count': len(units),
        'assignments': list(resolved.values()),
    }


def speaker_sample(session_path: Path, cluster_id: str) -> Path:
    if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_-]{0,99}', cluster_id):
        raise ValueError('Invalid voice cluster')
    paths = session_paths(session_path)
    if not paths['transcript_turns'].exists():
        raise FileNotFoundError('Speaker recognition has not finished')
    turns = [turn for turn in load_json(paths['transcript_turns']).get('turns', []) if turn['cluster_id'] == cluster_id]
    if not turns:
        raise FileNotFoundError('Voice cluster does not exist')
    best = max(turns, key=lambda turn: turn['end'] - turn['start'])
    duration = min(8.0, max(0.25, best['end'] - best['start']))
    start = max(0.0, best['start'])
    samples_dir = session_path / 'speaker-samples'
    samples_dir.mkdir(parents=True, exist_ok=True)
    sample_path = samples_dir / f'{cluster_id}.wav'
    if sample_path.exists():
        return sample_path
    command = [
        'ffmpeg', '-hide_banner', '-nostats', '-y', '-ss', str(start), '-t', str(duration), '-i', str(paths['audio']),
        '-ac', '1', '-ar', '16000', '-c:a', 'pcm_s16le', str(sample_path),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if completed.returncode != 0 or not sample_path.exists():
        raise SpeakerWorkflowError('A sample for this voice could not be created')
    return sample_path
