from services.ollama_client import OllamaClient
import pytest


class SyntheticResponse:
    status_code = 200
    ok = True

    def raise_for_status(self):
        return None

    def json(self):
        return {'embeddings': [[0.1, 0.2]]}


def test_embedding_requests_are_local_and_unload_after_ordinary_query(monkeypatch):
    calls = []

    def fake_post(url, **kwargs):
        calls.append((url, kwargs['json']))
        return SyntheticResponse()

    monkeypatch.setattr('services.ollama_client.requests.post', fake_post)
    client = OllamaClient('http://local-ollama:11434', 'gemma4:e4b', 'gemma4:e4b', 'embeddinggemma')

    assert client.embed('Where did I work?') == [0.1, 0.2]
    assert calls == [(
        'http://local-ollama:11434/api/embed',
        {'model': 'embeddinggemma', 'input': 'Where did I work?', 'keep_alive': 0},
    )]


def test_local_batch_unloads_both_models_after_failure(monkeypatch):
    events = []
    client = OllamaClient('http://local-ollama:11434', 'gemma4:e4b', 'gemma4:e4b', 'embeddinggemma')
    monkeypatch.setattr(client, 'is_reachable', lambda: True)
    monkeypatch.setattr(client, 'preload_analysis', lambda: events.append('load-analysis') or True)
    monkeypatch.setattr(client, 'preload_embeddings', lambda: events.append('load-embeddings') or True)
    monkeypatch.setattr(client, 'unload_embeddings', lambda: events.append('unload-embeddings') or True)
    monkeypatch.setattr(client, 'unload_analysis', lambda: events.append('unload-analysis') or True)

    with pytest.raises(RuntimeError, match='synthetic batch failure'):
        with client.local_embedding_batch():
            assert client._embedding_context.batch_active is True
            raise RuntimeError('synthetic batch failure')

    assert client._embedding_context.batch_active is False
    assert events == ['load-analysis', 'load-embeddings', 'unload-embeddings', 'unload-analysis']


def test_metadata_generation_uses_json_mode_and_analysis_budget(monkeypatch):
    calls = []

    class JsonResponse(SyntheticResponse):
        def json(self):
            return {'response': '{"title":"A complete local result"}'}

    def fake_post(url, **kwargs):
        calls.append((url, kwargs['json']))
        return JsonResponse()

    monkeypatch.setattr('services.ollama_client.requests.post', fake_post)
    monkeypatch.setattr('services.ollama_client.settings.ollama_analysis_max_tokens', 3072)
    client = OllamaClient('http://local-ollama:11434', 'gemma4:e4b', 'gemma4:e4b', 'embeddinggemma')

    assert client.generate_json('Return metadata')['title'] == 'A complete local result'
    request = calls[0][1]
    assert request['format'] == 'json'
    assert request['options']['temperature'] == 0
    assert request['options']['num_predict'] == 3072
