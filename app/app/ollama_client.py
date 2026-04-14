from __future__ import annotations

import json
from typing import Any

import httpx

from .config import get_settings


class OllamaError(RuntimeError):
    pass


async def _post_json(url: str, payload: dict[str, Any], timeout: float = 600.0) -> dict[str, Any]:
    async with httpx.AsyncClient(timeout=timeout) as client:
        response = await client.post(url, json=payload)
        response.raise_for_status()
        return response.json()


async def chat_json(prompt: str) -> dict[str, Any]:
    settings = get_settings()
    payload = {
        'model': settings.chat_model,
        'prompt': prompt,
        'stream': False,
        'format': 'json',
    }
    data = await _post_json(f"{settings.ollama_api_base}/api/generate", payload)
    try:
        return json.loads(data['response'])
    except Exception as exc:  # noqa: BLE001
        raise OllamaError(f'Failed to parse JSON response: {data}') from exc


async def chat_text(prompt: str) -> str:
    settings = get_settings()
    payload = {
        'model': settings.chat_model,
        'prompt': prompt,
        'stream': False,
    }
    data = await _post_json(f"{settings.ollama_api_base}/api/generate", payload)
    return data.get('response', '').strip()


async def embed_texts(texts: list[str]) -> list[list[float]]:
    settings = get_settings()
    payload = {
        'model': settings.embedding_model,
        'input': texts,
    }
    data = await _post_json(f"{settings.ollama_api_base}/api/embed", payload)
    return data.get('embeddings', [])


async def ollama_status() -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{settings.ollama_api_base}/api/tags")
            response.raise_for_status()
            tags = response.json().get('models', [])
            return {'reachable': True, 'models': tags}
        except Exception:  # noqa: BLE001
            return {'reachable': False, 'models': []}


async def bridge_call(action: str) -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=20.0) as client:
        response = await client.post(f"{settings.ollama_bridge_base}/{action}")
        response.raise_for_status()
        return response.json()


async def bridge_status() -> dict[str, Any]:
    settings = get_settings()
    async with httpx.AsyncClient(timeout=10.0) as client:
        try:
            response = await client.get(f"{settings.ollama_bridge_base}/status")
            response.raise_for_status()
            return response.json()
        except Exception:
            return {'bridge_available': False}
