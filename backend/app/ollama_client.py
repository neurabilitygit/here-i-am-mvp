from __future__ import annotations

import json
import requests
from typing import Any

from .config import OLLAMA_API_BASE, OLLAMA_MODEL, OLLAMA_EMBED_MODEL, OLLAMA_HOST_HELPER


def _post(url: str, payload: dict[str, Any], timeout: int = 300) -> dict[str, Any]:
    response = requests.post(url, json=payload, timeout=timeout)
    response.raise_for_status()
    return response.json()


def health() -> dict[str, Any]:
    try:
        response = requests.get(f"{OLLAMA_API_BASE}/api/tags", timeout=10)
        response.raise_for_status()
        return {"ok": True, "details": response.json()}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc)}


def helper_status() -> dict[str, Any]:
    try:
        response = requests.get(f"{OLLAMA_HOST_HELPER}/status", timeout=10)
        response.raise_for_status()
        return response.json()
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "error": str(exc), "helper_available": False}


def helper_start() -> dict[str, Any]:
    return _post(f"{OLLAMA_HOST_HELPER}/start", {})


def helper_stop() -> dict[str, Any]:
    return _post(f"{OLLAMA_HOST_HELPER}/stop", {})


def chat(system_prompt: str, user_prompt: str, model: str = OLLAMA_MODEL, timeout: int = 600) -> str:
    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        "stream": False,
    }
    data = _post(f"{OLLAMA_API_BASE}/api/chat", payload, timeout=timeout)
    return data["message"]["content"]


def embed(texts: list[str], model: str = OLLAMA_EMBED_MODEL, timeout: int = 300) -> list[list[float]]:
    payload = {"model": model, "input": texts}
    data = _post(f"{OLLAMA_API_BASE}/api/embed", payload, timeout=timeout)
    if "embeddings" in data:
        return data["embeddings"]
    if "embedding" in data:
        return [data["embedding"]]
    raise ValueError(f"Unexpected embedding response: {json.dumps(data)[:400]}")
