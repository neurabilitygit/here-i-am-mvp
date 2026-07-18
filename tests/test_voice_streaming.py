from models.schemas import VoiceStatus
from services import voice


class DummyResponse:
    status_code = 200
    ok = True
    headers = {'content-type': 'audio/wav'}
    content = b'RIFF-test-wav'

    def raise_for_status(self):
        return None

    def json(self):
        return {'status': 'canceling'}


def test_open_stream_forwards_request_identifier(monkeypatch):
    captured = {}
    monkeypatch.setattr(voice, 'load_voice_status', lambda: VoiceStatus(enabled=True, consented=True, provider='local'))
    monkeypatch.setattr(voice, '_release_local_chat_model', lambda: None)

    def fake_post(url, **kwargs):
        captured['url'] = url
        captured.update(kwargs)
        return DummyResponse()

    monkeypatch.setattr(voice.requests, 'post', fake_post)
    response, provider = voice.open_synthesis_stream('A short answer.', 1.0, 'voice-request-1')

    assert response.status_code == 200
    assert provider == 'local'
    assert captured['url'].endswith('/stream')
    assert captured['json']['request_id'] == 'voice-request-1'
    assert captured['stream'] is True


def test_cancel_stream_targets_the_matching_bridge_job(monkeypatch):
    captured = {}

    def fake_post(url, **kwargs):
        captured['url'] = url
        captured.update(kwargs)
        return DummyResponse()

    monkeypatch.setattr(voice.requests, 'post', fake_post)

    assert voice.cancel_synthesis_stream('voice-request-1') is True
    assert captured['url'].endswith('/cancel/voice-request-1')
    assert captured['timeout'] == 2


def test_batch_synthesis_forwards_request_id_and_uses_batch_timeout(monkeypatch):
    captured = {}
    monkeypatch.setattr(voice, 'load_voice_status', lambda: VoiceStatus(enabled=True, consented=True, provider='local'))
    monkeypatch.setattr(voice, '_release_local_chat_model', lambda: None)

    def fake_post(url, **kwargs):
        captured['url'] = url
        captured.update(kwargs)
        return DummyResponse()

    monkeypatch.setattr(voice.requests, 'post', fake_post)
    audio, media_type, provider = voice.synthesize('A complete answer.', 1.0, 'voice-batch-1')

    assert audio == b'RIFF-test-wav'
    assert media_type == 'audio/wav'
    assert provider == 'local'
    assert captured['url'].endswith('/synthesize')
    assert captured['json']['request_id'] == 'voice-batch-1'
    assert captured['timeout'] == (5, voice.settings.voice_batch_timeout_seconds)
