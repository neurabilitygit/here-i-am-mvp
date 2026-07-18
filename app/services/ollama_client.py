from __future__ import annotations

import json
import threading
import time
from contextlib import contextmanager
from typing import Any

import requests

from config import settings


class OllamaClient:
    def __init__(self, base_url: str, chat_model: str, analysis_model: str, embedding_model: str):
        self.base_url = base_url.rstrip("/")
        self.chat_model = chat_model
        self.analysis_model = analysis_model
        self.embedding_model = embedding_model
        self._embedding_context = threading.local()

    def is_reachable(self) -> bool:
        try:
            resp = requests.get(f"{self.base_url}/api/tags", timeout=10)
            return resp.ok
        except Exception:
            return False

    def installed_models(self) -> set[str]:
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=10)
            response.raise_for_status()
            models = response.json().get('models', [])
            names: set[str] = set()
            for model in models:
                name = str(model.get('name') or model.get('model') or '').strip()
                if name:
                    names.add(name)
                    names.add(name.removesuffix(':latest'))
            return names
        except Exception:
            return set()

    def has_model(self, model: str) -> bool:
        installed = self.installed_models()
        return model in installed or f'{model}:latest' in installed

    def control_status(self) -> dict[str, Any]:
        try:
            resp = requests.get(f"{settings.ollama_control_url}/status", timeout=10)
            if resp.ok:
                return resp.json()
            return {"status": "unavailable", "detail": f"HTTP {resp.status_code}"}
        except Exception as exc:
            return {"status": "unavailable", "detail": str(exc)}

    def start(self) -> dict[str, Any]:
        try:
            resp = requests.post(f"{settings.ollama_control_url}/start", headers={'X-Here-I-Am-Local': settings.local_bridge_token}, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"status": "unavailable", "detail": str(exc)}

    def stop(self) -> dict[str, Any]:
        try:
            resp = requests.post(f"{settings.ollama_control_url}/stop", headers={'X-Here-I-Am-Local': settings.local_bridge_token}, timeout=30)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            return {"status": "unavailable", "detail": str(exc)}

    def _generate(
        self,
        model: str,
        prompt: str,
        *,
        json_mode: bool = False,
        max_tokens: int | None = None,
    ) -> str:
        start = time.time()
        options = {"temperature": 0 if json_mode else settings.chat_temperature}
        if max_tokens is not None:
            options["num_predict"] = max_tokens
        elif model == self.chat_model:
            options["num_predict"] = settings.ollama_chat_max_tokens
        resp = requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": model,
                "prompt": prompt,
                "stream": False,
                "think": False,
                "keep_alive": settings.ollama_keep_alive,
                "options": options,
                **({"format": "json"} if json_mode else {}),
            },
            timeout=300,
        )
        resp.raise_for_status()
        data = resp.json()
        elapsed = time.time() - start
        print(f"[TIMING] ollama_generate model={model} elapsed={elapsed:.2f}s")
        return data.get("response", "").strip()

    def chat(self, prompt: str, *, json_mode: bool = False) -> str:
        return self._generate(self.chat_model, prompt, json_mode=json_mode)

    def analyze(self, prompt: str) -> str:
        return self._generate(
            self.analysis_model,
            prompt,
            max_tokens=settings.ollama_analysis_max_tokens,
        )

    def stream_chat(self, prompt: str):
        with requests.post(
            f"{self.base_url}/api/generate",
            json={
                "model": self.chat_model,
                "prompt": prompt,
                "stream": True,
                "think": False,
                "keep_alive": settings.ollama_keep_alive,
                "options": {
                    "temperature": settings.chat_temperature,
                    "num_predict": settings.ollama_chat_max_tokens,
                },
            },
            stream=True,
            timeout=300,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines(decode_unicode=True):
                if not line:
                    continue
                try:
                    event = json.loads(line)
                except json.JSONDecodeError:
                    continue
                token = event.get('response', '')
                if token:
                    yield token

    def preload(self) -> bool:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.chat_model, "prompt": "", "keep_alive": settings.ollama_keep_alive},
            timeout=300,
        )
        return response.ok

    def preload_embeddings(self) -> bool:
        response = requests.post(
            f"{self.base_url}/api/embed",
            json={
                "model": self.embedding_model,
                "input": "memory search warmup",
                "keep_alive": settings.ollama_keep_alive,
            },
            timeout=300,
        )
        return response.ok

    def preload_analysis(self) -> bool:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.analysis_model, "prompt": "", "stream": False, "keep_alive": settings.ollama_keep_alive},
            timeout=300,
        )
        return response.ok

    def unload_chat(self) -> bool:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.chat_model, "keep_alive": 0},
            timeout=30,
        )
        return response.ok

    def unload_analysis(self) -> bool:
        response = requests.post(
            f"{self.base_url}/api/generate",
            json={"model": self.analysis_model, "keep_alive": 0},
            timeout=30,
        )
        return response.ok

    def unload_embeddings(self) -> bool:
        response = requests.post(
            f"{self.base_url}/api/embed",
            json={"model": self.embedding_model, "input": "", "keep_alive": 0},
            timeout=30,
        )
        return response.ok

    @contextmanager
    def local_embedding_batch(self):
        """Keep local Gemma models resident only for one explicit indexing batch."""
        if not self.is_reachable():
            raise RuntimeError("Local Ollama is not running")
        if not self.preload_analysis():
            raise RuntimeError(f"Could not load local analysis model {self.analysis_model}")
        if not self.preload_embeddings():
            self.unload_analysis()
            raise RuntimeError(f"Could not load local embedding model {self.embedding_model}")
        self._embedding_context.batch_active = True
        try:
            yield
        finally:
            self._embedding_context.batch_active = False
            try:
                self.unload_embeddings()
            finally:
                self.unload_analysis()

    def preload_all(self) -> bool:
        return self.preload() and self.preload_embeddings()

    def generate_json(self, prompt: str) -> dict[str, Any]:
        raw = self._generate(
            self.analysis_model,
            prompt,
            json_mode=True,
            max_tokens=settings.ollama_analysis_max_tokens,
        ).strip()

        if raw.startswith("```"):
            lines = raw.splitlines()
            if len(lines) >= 3:
                raw = "\n".join(lines[1:-1]).strip()

        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            raw = raw[start:end + 1]

        try:
            return json.loads(raw)
        except json.JSONDecodeError as exc:
            raise RuntimeError(f"Model did not return valid JSON: {raw[:500]}") from exc

    def _embed_one_legacy(self, text: str) -> list[float]:
        start = time.time()
        legacy = requests.post(
            f"{self.base_url}/api/embeddings",
            json={
                "model": self.embedding_model,
                "prompt": text,
                "keep_alive": settings.ollama_keep_alive if getattr(self._embedding_context, 'batch_active', False) else 0,
            },
            timeout=300,
        )
        legacy.raise_for_status()
        data = legacy.json()
        elapsed = time.time() - start
        print(f"[TIMING] ollama_embed_legacy model={self.embedding_model} elapsed={elapsed:.2f}s")
        embedding = data.get("embedding")
        if not embedding:
            raise RuntimeError("Ollama legacy embeddings response did not contain 'embedding'.")
        return embedding

    def embed(self, input: str | list[str]) -> list[float] | list[list[float]]:
        if isinstance(input, str):
            single = True
            values = [input]
        else:
            single = False
            values = input

        start = time.time()
        resp = requests.post(
            f"{self.base_url}/api/embed",
            json={
                "model": self.embedding_model,
                "input": values if not single else values[0],
                "keep_alive": settings.ollama_keep_alive if getattr(self._embedding_context, 'batch_active', False) else 0,
            },
            timeout=300,
        )

        if resp.status_code == 404:
            embeddings = [self._embed_one_legacy(text) for text in values]
            elapsed = time.time() - start
            print(f"[TIMING] ollama_embed_fallback_batch model={self.embedding_model} count={len(values)} elapsed={elapsed:.2f}s")
            return embeddings[0] if single else embeddings

        resp.raise_for_status()
        data = resp.json()
        embeddings = data.get("embeddings")
        elapsed = time.time() - start
        print(f"[TIMING] ollama_embed model={self.embedding_model} count={len(values)} elapsed={elapsed:.2f}s")
        if not embeddings or not isinstance(embeddings, list):
            raise RuntimeError("Ollama embed response did not contain 'embeddings'.")
        return embeddings[0] if single else embeddings


ollama_client = OllamaClient(
    base_url=settings.ollama_base_url,
    chat_model=settings.ollama_chat_model,
    analysis_model=settings.ollama_analysis_model,
    embedding_model=settings.ollama_embedding_model,
)
