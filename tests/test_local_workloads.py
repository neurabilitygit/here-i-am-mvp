import subprocess
import sys
import threading
from types import SimpleNamespace

import pytest
import requests

from config import settings
from services import local_workloads as workloads
from services.ollama_client import OllamaClient


def test_claim_is_reentrant_but_rejects_other_threads_and_releases_on_error(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, 'local_workload_lock_path', str(tmp_path / 'inference.lock'))
    gate = workloads.LocalWorkloads()
    outcomes = []
    def competitor():
        try:
            with gate.claim('chat'):
                outcomes.append('entered')
        except workloads.LocalWorkloadBusy:
            outcomes.append('busy')
    with pytest.raises(ValueError):
        with gate.claim('batch'):
            with gate.claim('analysis'):
                worker = threading.Thread(target=competitor)
                worker.start()
                worker.join(2)
                assert outcomes == ['busy']
                raise ValueError('synthetic')
    with gate.claim('voice'):
        pass


def test_claim_blocks_another_process(tmp_path, monkeypatch):
    path = str(tmp_path / 'inference.lock')
    monkeypatch.setattr(settings, 'local_workload_lock_path', path)
    code = "import sys,fcntl; f=open(sys.argv[1],'a+'); fcntl.flock(f.fileno(),fcntl.LOCK_EX|fcntl.LOCK_NB)"
    with workloads.LocalWorkloads().claim('voice'):
        result = subprocess.run([sys.executable, '-c', code, path], capture_output=True)
    assert result.returncode != 0
    assert b'BlockingIOError' in result.stderr
    assert subprocess.run([sys.executable, '-c', code, path], capture_output=True).returncode == 0


def test_embedding_can_run_while_another_thread_owns_heavy_slot(monkeypatch):
    monkeypatch.setattr('services.ollama_client.requests.post', lambda *a, **kw: SimpleNamespace(status_code=200, raise_for_status=lambda:None, json=lambda:{'embeddings':[[.1,.2]]}))
    client = OllamaClient('http://local', 'chat', 'analysis', 'embed')
    results = []
    with workloads.local_workloads.claim('voice'):
        thread = threading.Thread(target=lambda: results.append(client.embed('synthetic')))
        thread.start()
        thread.join(2)
    assert results == [[.1,.2]]


def test_generator_holds_slot_until_closed():
    @workloads.exclusive_local_workload('chat')
    def stream():
        yield 'one'
        yield 'two'
    generator = stream()
    assert next(generator) == 'one'
    blocked = []
    def other():
        try:
            with workloads.local_workloads.claim('voice'):
                blocked.append(False)
        except workloads.LocalWorkloadBusy:
            blocked.append(True)
    thread = threading.Thread(target=other)
    thread.start()
    thread.join(2)
    generator.close()
    assert blocked == [True]
    with workloads.local_workloads.claim('voice'):
        pass


def test_voice_busy_and_incompatible_unload_fail_closed(monkeypatch):
    monkeypatch.setattr(settings, 'local_bridge_token', 'synthetic-test-token')
    status = {'busy':True}
    monkeypatch.setattr(workloads.requests, 'get', lambda *a, **kw: SimpleNamespace(raise_for_status=lambda:None, json=lambda:status))
    with pytest.raises(workloads.LocalWorkloadBusy, match='still preparing'):
        workloads.release_idle_voice()
    status.update(busy=False, model_loaded=True)
    def unavailable(*a, **kw):
        raise requests.HTTPError('synthetic 404')
    monkeypatch.setattr(workloads.requests, 'post', unavailable)
    with pytest.raises(workloads.LocalWorkloadBusy, match='same version'):
        workloads.release_idle_voice()


def test_voice_connect_timeout_is_not_treated_as_a_stopped_bridge(monkeypatch):
    monkeypatch.setattr(settings, 'local_bridge_token', 'synthetic-test-token')
    def timeout(*a, **kw):
        raise requests.ConnectTimeout('synthetic timeout')
    monkeypatch.setattr(workloads.requests, 'get', timeout)
    with pytest.raises(workloads.LocalWorkloadBusy, match='could not be checked'):
        workloads.release_idle_voice()


def test_transcription_releases_cached_model_on_failure(monkeypatch):
    from services import pipeline
    model = object()
    monkeypatch.setattr(pipeline, '_whisper_model', model)
    monkeypatch.setattr(pipeline, 'prepare_transcription_memory', lambda:None)
    with pytest.raises(ValueError):
        with pipeline.local_transcription_model() as loaded:
            assert loaded is model
            raise ValueError('synthetic')
    assert pipeline._whisper_model is None


def test_language_context_is_explicit_and_stream_cancellation_does_not_leak_threads(monkeypatch):
    monkeypatch.setattr('services.ollama_client.release_idle_voice', lambda:None)
    calls = []
    class Response:
        def __enter__(self): return self
        def __exit__(self, *args): return None
        def raise_for_status(self): pass
        def close(self): pass
        def iter_lines(self, **kwargs):
            yield '{"response":"Hello"}'
            yield '{"done":true,"eval_count":1,"eval_duration":1000000000}'
    def post(url, **kwargs):
        calls.append(kwargs['json'])
        return Response()
    monkeypatch.setattr('services.ollama_client.requests.post', post)
    before = {thread for thread in threading.enumerate() if thread.name == 'ollama-stream-cancel'}
    client = OllamaClient('http://local', 'chat', 'analysis', 'embed')
    assert list(client.stream_chat('synthetic', cancel_event=threading.Event())) == ['Hello']
    for thread in threading.enumerate():
        if thread.name == 'ollama-stream-cancel' and thread not in before:
            thread.join(1)
            assert not thread.is_alive()
    assert calls[0]['options']['num_ctx'] == settings.ollama_chat_context_tokens
    assert client.last_metrics('generation')['eval_count'] == 1
