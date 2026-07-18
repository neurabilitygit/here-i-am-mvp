from __future__ import annotations

import json
import logging
import threading
from pathlib import Path

from config import settings
from models.schemas import ExperiencePreferences
from services.storage import atomic_write_text


_lock = threading.RLock()
_runtime_cloud_key = ''
logger = logging.getLogger('here_i_am.preferences')


def _default_preferences() -> ExperiencePreferences:
    return ExperiencePreferences(provider=settings.text_provider, cloud_model=settings.openai_model)


def load_preferences() -> ExperiencePreferences:
    path = Path(settings.preferences_path)
    with _lock:
        if not path.exists():
            return _default_preferences()
        try:
            return ExperiencePreferences.model_validate_json(path.read_text(encoding='utf-8'))
        except Exception as exc:
            logger.error('preferences file is invalid; using configured defaults: %s', exc)
            return _default_preferences()


def save_preferences(preferences: ExperiencePreferences) -> ExperiencePreferences:
    with _lock:
        atomic_write_text(Path(settings.preferences_path), preferences.model_dump_json(indent=2))
    return preferences


def set_runtime_cloud_key(value: str | None) -> None:
    global _runtime_cloud_key
    if value is not None:
        if value.strip() and not settings.allow_runtime_cloud_key:
            raise RuntimeError('Entering a cloud key in the browser is disabled in this production configuration')
        _runtime_cloud_key = value.strip()


def cloud_api_key() -> tuple[str, str]:
    if _runtime_cloud_key:
        return _runtime_cloud_key, 'session'
    if settings.openai_api_key:
        return settings.openai_api_key, 'environment'
    if settings.openai_api_key_file:
        try:
            value = Path(settings.openai_api_key_file).read_text(encoding='utf-8').strip()
            if value:
                return value, 'environment'
        except OSError:
            logger.error('configured OpenAI key file is unavailable')
    return '', 'none'


def public_preferences() -> dict:
    preferences = load_preferences()
    key, source = cloud_api_key()
    return {
        'preferences': preferences.model_dump(mode='json'),
        'cloud_configured': bool(key),
        'cloud_key_source': source,
        'runtime_cloud_key_allowed': settings.allow_runtime_cloud_key,
        'allowed_cloud_models': settings.allowed_openai_model_list,
    }
