from __future__ import annotations

import json
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator

import requests

from config import settings
from services.ollama_client import ollama_client
from services.preferences import cloud_api_key, load_preferences
from services.jsonl_store import append_jsonl


_audit_lock = threading.Lock()


@dataclass
class GenerationResult:
    text: str
    provider: str
    model: str
    elapsed_seconds: float
    first_token_seconds: float | None = None


def _append_audit(record: dict) -> None:
    path = Path(settings.generation_audit_path)
    path.parent.mkdir(parents=True, exist_ok=True)
    value = {'timestamp': datetime.now(timezone.utc).isoformat(), **record}
    with _audit_lock:
        append_jsonl(path, value)


class LocalProvider:
    name = 'local'

    @staticmethod
    def _prompt(prompt: str) -> str:
        if 'RESPONSE_KIND\nNARRATIVE_PERSONAL' not in prompt:
            return prompt
        return f"""{prompt}

LOCAL_ENGINE_LENGTH_OVERRIDE
For this narrative personal answer, target 120 to 160 words in six to ten complete sentences.
When the evidence supports it, weave together at least three distinct relevant facts or memories instead of stopping after the first one.
Do not pad the answer, repeat the same fact, or invent connective details. If the evidence cannot support 120 words, stop rather than speculate.
"""

    def generate(self, prompt: str, *, json_mode: bool = False) -> GenerationResult:
        started = time.perf_counter()
        text = ollama_client.chat(self._prompt(prompt), json_mode=json_mode)
        result = GenerationResult(text=text, provider=self.name, model=ollama_client.chat_model, elapsed_seconds=time.perf_counter() - started)
        _append_audit({'provider': result.provider, 'model': result.model, 'elapsed_seconds': result.elapsed_seconds, 'characters': len(text), 'streamed': False, 'outcome': 'success'})
        return result

    def stream(self, prompt: str) -> Iterator[str]:
        yield from ollama_client.stream_chat(self._prompt(prompt))


class OpenAIProvider:
    name = 'openai'

    def __init__(self, model: str):
        self.model = model
        self.last_usage: dict = {}
        self.last_response_id = ''

    def _headers(self) -> dict[str, str]:
        key, _source = cloud_api_key()
        if not key:
            raise RuntimeError('Cloud mode is selected, but no cloud API key is configured')
        return {'Authorization': f'Bearer {key}', 'Content-Type': 'application/json'}

    def _payload(self, prompt: str, *, stream: bool, json_mode: bool = False) -> dict:
        payload = {
            'model': self.model,
            'instructions': 'Follow the supplied grounding and voice-fidelity contract exactly.',
            'input': prompt,
            'stream': stream,
            'store': settings.cloud_store_responses,
        }
        if not self.model.startswith('gpt-5'):
            payload['temperature'] = settings.chat_temperature
        if json_mode:
            payload['text'] = {'format': {'type': 'json_object'}}
        return payload

    def generate(self, prompt: str, *, json_mode: bool = False) -> GenerationResult:
        started = time.perf_counter()
        response = requests.post(
            f'{settings.openai_base_url.rstrip("/")}/responses',
            headers=self._headers(),
            json=self._payload(prompt, stream=False, json_mode=json_mode),
            timeout=(settings.provider_connect_timeout_seconds, settings.provider_read_timeout_seconds),
        )
        response.raise_for_status()
        body = response.json()
        usage = body.get('usage') or {}
        text = body.get('output_text') or ''.join(
            item.get('text', '')
            for output in body.get('output', [])
            for item in output.get('content', [])
            if item.get('type') == 'output_text'
        )
        result = GenerationResult(text=text.strip(), provider=self.name, model=self.model, elapsed_seconds=time.perf_counter() - started)
        _append_audit({
            'provider': result.provider,
            'model': result.model,
            'elapsed_seconds': result.elapsed_seconds,
            'characters': len(result.text),
            'streamed': False,
            'outcome': 'success',
            'response_id': str(body.get('id') or ''),
            'input_tokens': usage.get('input_tokens'),
            'output_tokens': usage.get('output_tokens'),
        })
        return result

    def stream(self, prompt: str) -> Iterator[str]:
        with requests.post(
            f'{settings.openai_base_url.rstrip("/")}/responses',
            headers=self._headers(),
            json=self._payload(prompt, stream=True),
            stream=True,
            timeout=(settings.provider_connect_timeout_seconds, settings.provider_read_timeout_seconds),
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line or not line.startswith('data: '):
                    continue
                value = line[6:]
                if value == '[DONE]':
                    break
                try:
                    event = json.loads(value)
                except json.JSONDecodeError:
                    continue
                if event.get('type') == 'response.output_text.delta':
                    delta = event.get('delta', '')
                    if delta:
                        yield delta
                elif event.get('type') == 'response.completed':
                    completed = event.get('response') or {}
                    self.last_response_id = str(completed.get('id') or '')
                    self.last_usage = completed.get('usage') or {}


def provider_for(name: str, model: str | None = None):
    if name == 'openai':
        preferences = load_preferences()
        return OpenAIProvider(model or preferences.cloud_model or settings.openai_model)
    if name == 'local':
        return LocalProvider()
    raise ValueError(f'Unknown text provider: {name}')


def active_provider():
    preferences = load_preferences()
    return provider_for(preferences.provider)


def validate_provider_selection(preferences, proposed_cloud_key: str | None = None) -> None:
    if preferences.provider == 'local':
        if not ollama_client.is_reachable():
            raise RuntimeError('Local Gemma is not running. Start Ollama before selecting the private local engine.')
        if not ollama_client.has_model(ollama_client.chat_model):
            raise RuntimeError(f'The configured local model {ollama_client.chat_model} is not installed.')
        return

    if preferences.cloud_model not in settings.allowed_openai_model_list:
        raise RuntimeError('That OpenAI model is not approved for this installation.')
    key = proposed_cloud_key.strip() if proposed_cloud_key is not None else cloud_api_key()[0]
    if not key:
        raise RuntimeError('OpenAI is not configured. Add the API key to the production environment first.')


def transition_provider(previous: str, current: str) -> None:
    if previous == current:
        return
    try:
        if current == 'openai' and ollama_client.is_reachable():
            ollama_client.unload_chat()
        elif current == 'local' and ollama_client.is_reachable():
            ollama_client.preload()
    except Exception:
        # Readiness is reported separately. A resource optimization must never
        # roll back an already validated and persisted user choice.
        return


def public_provider_error(provider: str, exc: Exception) -> str:
    if provider == 'openai':
        if isinstance(exc, requests.Timeout):
            return 'OpenAI took too long to answer. Your provider setting was not changed.'
        if isinstance(exc, requests.HTTPError) and exc.response is not None and exc.response.status_code in {401, 403}:
            return 'OpenAI could not authenticate. Check the configured production API key.'
        return 'OpenAI could not complete this answer. Your provider setting was not changed.'
    if isinstance(exc, requests.Timeout):
        return 'Local Gemma took too long to answer. You can retry or select Best answer in Settings.'
    return 'Local Gemma is unavailable. Start Ollama or select Best answer in Settings.'


def record_stream_audit(
    provider: str,
    model: str,
    elapsed_seconds: float,
    characters: int,
    *,
    response_id: str = '',
    usage: dict | None = None,
) -> None:
    usage = usage or {}
    _append_audit({
        'provider': provider,
        'model': model,
        'elapsed_seconds': elapsed_seconds,
        'characters': characters,
        'streamed': True,
        'outcome': 'success',
        'response_id': response_id,
        'input_tokens': usage.get('input_tokens'),
        'output_tokens': usage.get('output_tokens'),
    })


def record_generation_failure(provider: str, model: str, elapsed_seconds: float, exc: Exception) -> None:
    _append_audit({
        'provider': provider,
        'model': model,
        'elapsed_seconds': elapsed_seconds,
        'streamed': False,
        'outcome': 'failure',
        'error_type': type(exc).__name__,
    })


def provider_status() -> dict:
    preferences = load_preferences()
    key, source = cloud_api_key()
    local_model_available = ollama_client.has_model(ollama_client.chat_model)
    local_ready = ollama_client.is_reachable() and local_model_available
    cloud_model_allowed = preferences.cloud_model in settings.allowed_openai_model_list
    cloud_ready = bool(key) and cloud_model_allowed
    return {
        'active': preferences.provider,
        'local_ready': local_ready,
        'local_model': ollama_client.chat_model,
        'local_model_available': local_model_available,
        'cloud_configured': bool(key),
        'cloud_key_source': source,
        'cloud_model': preferences.cloud_model,
        'cloud_model_allowed': cloud_model_allowed,
        'active_ready': local_ready if preferences.provider == 'local' else cloud_ready,
        'no_automatic_fallback': True,
        'embedding_provider': 'local_ollama',
        'embedding_model': ollama_client.embedding_model,
    }
