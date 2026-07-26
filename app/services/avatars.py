from __future__ import annotations

import base64
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

import requests

from config import settings
from services.jobs import job_manager
from services.preferences import cloud_api_key
from services.speakers import get_speaker_record, safe_speaker_id, update_speaker_record


class AvatarWorkflowError(RuntimeError):
    pass


def _speaker_dir(speaker_id: str) -> Path:
    safe_speaker_id(speaker_id)
    path = Path(settings.speakers_dir) / speaker_id
    path.mkdir(parents=True, exist_ok=True)
    return path


def _probe_image(path: Path) -> None:
    completed = subprocess.run(
        ['ffprobe', '-v', 'error', '-select_streams', 'v:0', '-show_entries', 'stream=width,height', '-of', 'json', str(path)],
        capture_output=True,
        text=True,
        timeout=30,
    )
    if completed.returncode != 0 or 'width' not in completed.stdout or 'height' not in completed.stdout:
        raise AvatarWorkflowError('The selected file is not a readable image')


def _normalize_avatar(source: Path, destination: Path) -> None:
    command = [
        'ffmpeg', '-hide_banner', '-nostats', '-y', '-i', str(source),
        '-vf',
        'scale=768:768:force_original_aspect_ratio=decrease,'
        'pad=768:768:(ow-iw)/2:(oh-ih)/2:color=0xF2E6D0',
        '-frames:v', '1', '-c:v', 'libwebp', '-quality', '90', str(destination),
    ]
    completed = subprocess.run(command, capture_output=True, text=True, timeout=120)
    if completed.returncode != 0 or not destination.exists():
        raise AvatarWorkflowError('The avatar image could not be prepared')


def store_speaker_image(speaker_id: str, uploaded_path: Path, *, kind: str, original_name: str) -> dict[str, Any]:
    if kind not in {'avatar', 'photo'}:
        raise ValueError('Image kind must be avatar or photo')
    _probe_image(uploaded_path)
    record = get_speaker_record(speaker_id)
    image_id = uuid.uuid4().hex
    root = _speaker_dir(speaker_id)
    safe_suffix = Path(original_name).suffix.lower()
    if safe_suffix not in {'.jpg', '.jpeg', '.png', '.webp', '.heic', '.heif'}:
        safe_suffix = '.image'
    stored_source = root / f'{kind}-source-{image_id}{safe_suffix}'
    shutil.move(str(uploaded_path), stored_source)
    updates: dict[str, Any]
    if kind == 'avatar':
        avatar_path = root / f'avatar-{image_id}.webp'
        _normalize_avatar(stored_source, avatar_path)
        avatars = list(record.get('avatars') or [])
        avatars.append({'avatar_id': image_id, 'path': str(avatar_path), 'origin': 'uploaded'})
        updates = {'avatars': avatars, 'active_avatar_id': image_id}
    else:
        photos = list(record.get('source_photos') or [])
        photos.append({'photo_id': image_id, 'path': str(stored_source)})
        updates = {'source_photos': photos, 'active_source_photo_id': image_id}
    updated = update_speaker_record(speaker_id, **updates)
    return {
        'speaker_id': speaker_id,
        'kind': kind,
        'image_id': image_id,
        'avatar_url': f'/api/speakers/{speaker_id}/avatar' if updated.get('active_avatar_id') else None,
        'can_generate': bool(updated.get('active_source_photo_id')),
    }


def active_avatar_path(speaker_id: str) -> Path:
    record = get_speaker_record(speaker_id)
    active_id = record.get('active_avatar_id')
    avatar = next((item for item in record.get('avatars', []) if item.get('avatar_id') == active_id), None)
    if not avatar:
        raise FileNotFoundError('This speaker does not have an avatar yet')
    path = Path(avatar['path'])
    if not path.exists():
        raise FileNotFoundError('The active avatar file is missing')
    return path


def _active_source_photo(record: dict[str, Any]) -> Path:
    active_id = record.get('active_source_photo_id')
    photo = next((item for item in record.get('source_photos', []) if item.get('photo_id') == active_id), None)
    if not photo or not Path(photo['path']).exists():
        raise AvatarWorkflowError('Upload a face photo for this speaker first')
    return Path(photo['path'])


def validate_avatar_generation(speaker_id: str) -> None:
    record = get_speaker_record(speaker_id)
    _active_source_photo(record)
    api_key, _ = cloud_api_key()
    if not api_key:
        raise AvatarWorkflowError('OpenAI image generation is not configured')


def generate_avatar(job_id: str, speaker_id: str) -> None:
    record = get_speaker_record(speaker_id)
    source_photo = _active_source_photo(record)
    api_key, _ = cloud_api_key()
    if not api_key:
        raise AvatarWorkflowError('OpenAI image generation is not configured')
    job_manager.update(job_id, status='running', total=1, message=f"Illustrating {record['display_name']}")
    style_reference = Path(__file__).resolve().parents[1] / 'static' / 'assets' / 'eric-bass-avatar-flat.webp'
    prompt = (
        'Create a square, warm, non-photorealistic illustrated avatar for the Here I Am memory application. '
        'The first supplied image is the identity reference: preserve the recognizable face shape, age, expression, '
        'skin tone, hair, and distinctive facial features without making a photographic copy. '
        'The second supplied image is style reference only: match its simplified hand-drawn shapes, soft tactile texture, '
        'warm dusk palette, friendly eyes, gentle dimensional shading, and calm optimistic character. '
        'Head and shoulders, centered, uncluttered warm background, dignified and welcoming for adults over 55. '
        'No words, logos, photorealism, exaggerated caricature, or additional people.'
    )
    files: list[tuple[str, tuple[str, Any, str]]] = []
    handles = []
    try:
        photo_handle = source_photo.open('rb')
        handles.append(photo_handle)
        files.append(('image[]', (source_photo.name, photo_handle, 'application/octet-stream')))
        if style_reference.exists():
            style_handle = style_reference.open('rb')
            handles.append(style_handle)
            files.append(('image[]', (style_reference.name, style_handle, 'image/webp')))
        response = requests.post(
            f"{settings.openai_base_url.rstrip('/')}/images/edits",
            headers={'Authorization': f'Bearer {api_key}'},
            data={
                'model': settings.avatar_image_model,
                'prompt': prompt,
                'size': '1024x1024',
                'quality': settings.avatar_image_quality,
                'output_format': 'png',
                'input_fidelity': 'high',
            },
            files=files,
            timeout=(settings.provider_connect_timeout_seconds, 600),
        )
        response.raise_for_status()
        payload = response.json()
    finally:
        for handle in handles:
            handle.close()
    data = payload.get('data') if isinstance(payload, dict) else None
    first = data[0] if isinstance(data, list) and data else {}
    encoded = first.get('b64_json') if isinstance(first, dict) else None
    if not encoded:
        raise AvatarWorkflowError('The image service returned no avatar')
    try:
        image_bytes = base64.b64decode(encoded, validate=True)
    except ValueError as exc:
        raise AvatarWorkflowError('The generated avatar was not a valid image') from exc

    avatar_id = uuid.uuid4().hex
    root = _speaker_dir(speaker_id)
    raw_path = root / f'avatar-generated-{avatar_id}.png'
    avatar_path = root / f'avatar-{avatar_id}.webp'
    raw_path.write_bytes(image_bytes)
    _probe_image(raw_path)
    _normalize_avatar(raw_path, avatar_path)
    avatars = list(record.get('avatars') or [])
    avatars.append({'avatar_id': avatar_id, 'path': str(avatar_path), 'origin': 'generated'})
    update_speaker_record(speaker_id, avatars=avatars, active_avatar_id=avatar_id)
    job_manager.update(
        job_id,
        status='done',
        message=f"{record['display_name']}'s illustrated avatar is ready",
        processed=1,
        total=1,
        completed=True,
        result={'speaker_id': speaker_id, 'avatar_url': f'/api/speakers/{speaker_id}/avatar?v={avatar_id}'},
    )
