from fastapi.testclient import TestClient
from types import SimpleNamespace
from pathlib import Path
from io import BytesIO
import time
import wave

import main
from config import settings
from models.schemas import BenchmarkAnswer, ChatBenchmarkResponse, ChatResponse
from services.preferences import load_preferences
from services.storage import ensure_directories


client = TestClient(main.app)


def test_health_and_security_headers():
    ensure_directories()
    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.headers['x-content-type-options'] == 'nosniff'
    assert response.headers['x-frame-options'] == 'DENY'
    assert response.headers['content-security-policy'].startswith("default-src 'self'")
    assert 'camera=()' in response.headers['permissions-policy']
    assert 'Selected answer engine' in client.get('/').text
    assert client.get('/docs').status_code == 404
    assert response.headers['x-request-id']


def test_cross_origin_mutation_is_rejected():
    response = client.post(
        '/api/fidelity/rebuild',
        headers={'Origin': 'https://malicious.example'},
    )
    assert response.status_code == 403


def test_session_and_reconciliation_contracts():
    response = client.get('/api/sessions')
    assert response.status_code == 200
    assert isinstance(response.json(), list)
    report = client.get('/api/reconciliation')
    assert report.status_code == 200
    assert report.json()['repair_applied'] is False


def test_audio_upload_enters_the_unprocessed_memory_queue():
    audio = BytesIO()
    with wave.open(audio, 'wb') as recording:
        recording.setnchannels(1)
        recording.setsampwidth(2)
        recording.setframerate(16000)
        recording.writeframes(b'\0\0' * 1600)

    response = client.post(
        '/api/recordings/upload',
        files={'file': ('A Family Story.wav', audio.getvalue(), 'audio/wav')},
        data={'title': 'A Family Story'},
    )

    assert response.status_code == 200
    payload = response.json()
    assert 'a-family-story' in payload['session_id']
    assert 'flac_path' not in payload
    assert 'session_path' not in payload
    assert (Path(settings.sessions_dir) / payload['session_id'] / 'recording.flac').exists()
    status = client.get('/api/memory-batch/status').json()
    assert status['queued_recordings'] >= 1


def test_chat_response_remains_backward_compatible(monkeypatch):
    monkeypatch.setattr(main, 'provider_status', lambda: {'active': 'local', 'active_ready': True})
    monkeypatch.setattr(main, 'answer_question', lambda _question: ChatResponse(answer='Synthetic answer', mode='GENERAL'))
    response = client.post('/api/chat', json={'question': 'Synthetic question'})
    assert response.status_code == 200
    assert response.json()['answer'] == 'Synthetic answer'
    assert response.json()['sources'] == []


def test_stream_sends_heartbeat_while_provider_is_working(monkeypatch):
    class SlowProvider:
        name = 'local'

        def stream(self, _prompt):
            time.sleep(0.03)
            yield 'Ready.'

    monkeypatch.setattr(main, 'provider_status', lambda: {'active': 'local', 'active_ready': True})
    monkeypatch.setattr(main, 'active_provider', lambda: SlowProvider())
    monkeypatch.setattr(main, 'prepare_answer', lambda _question: SimpleNamespace(
        mode='GENERAL', sources=[], prompt='Synthetic prompt', retrieval_seconds=0.0,
    ))
    monkeypatch.setattr(main.settings, 'provider_stream_heartbeat_seconds', 0.01)
    monkeypatch.setattr(main, 'record_stream_audit', lambda *_args, **_kwargs: None)

    response = client.post('/api/chat/stream', json={'question': 'Synthetic question'})

    assert response.status_code == 200
    assert ': keep-alive' in response.text
    assert 'Ready.' in response.text


def test_talk_benchmark_compares_same_prepared_question(monkeypatch):
    monkeypatch.setattr(main, 'benchmark_question', lambda question: ChatBenchmarkResponse(
        question=question,
        mode='PERSONAL',
        retrieval_seconds=0.25,
        results=[
            BenchmarkAnswer(provider='local', model='gemma4:e4b', answer='Local answer', elapsed_seconds=9.0),
            BenchmarkAnswer(provider='openai', model='gpt-5.4', answer='Cloud answer', elapsed_seconds=3.0),
        ],
    ))
    response = client.post('/api/chat/benchmark', json={'question': 'What did I say about baseball?'})
    assert response.status_code == 200
    assert [item['provider'] for item in response.json()['results']] == ['local', 'openai']
    assert response.json()['question'] == 'What did I say about baseball?'


def test_reindex_requires_explicit_confirmation():
    response = client.post('/api/vector/reindex/start')
    assert response.status_code == 400
    plan = client.get('/api/vector/reindex-plan')
    assert plan.status_code == 200
    assert plan.json()['writes_performed'] is False


def test_memory_batch_is_local_only_and_requires_confirmation():
    status = client.get('/api/memory-batch/status')
    assert status.status_code == 200
    assert status.json()['embedding_provider'] == 'local_ollama'
    assert status.json()['openai_embedding_enabled'] is False
    assert status.json()['analysis_model'] == 'gemma4:e4b'
    assert status.json()['embedding_model'] == 'embeddinggemma'
    assert 'last_job' in status.json()

    denied = client.post('/api/memory-batch/start')
    assert denied.status_code == 400
    assert 'unavailable' in denied.json()['detail'].lower()


def test_experience_and_voice_contracts():
    experience = client.get('/api/experience')
    assert experience.status_code == 200
    assert 'cloud_api_key' not in experience.text
    assert experience.json()['preferences']['avatar']['name']

    voice = client.get('/api/voice/status')
    assert voice.status_code == 200
    assert voice.json()['consented'] is False

    denied = client.post('/api/voice/prepare', json={
        'session_id': 'missing', 'confirm_voice_rights': False, 'provider': 'local',
    })
    assert denied.status_code == 400


def test_invalid_provider_switch_is_not_persisted(monkeypatch):
    before = load_preferences()
    candidate = before.model_copy(deep=True)
    candidate.provider = 'openai' if before.provider == 'local' else 'local'

    def reject(_preferences, _key=None):
        raise RuntimeError('Selected provider is not ready')

    monkeypatch.setattr(main, 'validate_provider_selection', reject)
    response = client.put('/api/experience', json={'preferences': candidate.model_dump(mode='json')})

    assert response.status_code == 409
    assert load_preferences().provider == before.provider


def test_voice_cancel_contract(monkeypatch):
    monkeypatch.setattr(main, 'cancel_synthesis_stream', lambda request_id: request_id == 'voice-request-1')

    canceled = client.post('/api/voice/cancel/voice-request-1')
    assert canceled.status_code == 200
    assert canceled.json()['status'] == 'canceling'

    invalid = client.post('/api/voice/cancel/not%20valid')
    assert invalid.status_code == 400
