from models.schemas import VoiceStatus
from services import voice
from services.storage import create_session_dir, session_paths, update_processing_state


class DummyResponse:
    status_code = 200
    ok = True
    headers = {'content-type': 'audio/wav'}
    content = b'RIFF-test-wav'

    def raise_for_status(self):
        return None

    def json(self):
        return {'status': 'canceling'}


def test_global_voice_candidates_exclude_mixed_conversation_audio(monkeypatch):
    _session_id, session = create_session_dir('mixed voices')
    paths = session_paths(session)
    paths['audio'].write_bytes(b'not-real-audio')
    paths['transcript'].write_text('word ' * 100, encoding='utf-8')
    update_processing_state(session, recording_mode='conversation', speaker_review_status='complete')
    monkeypatch.setattr(voice, 'list_session_dirs', lambda: [session])
    monkeypatch.setattr(voice, '_duration', lambda _path: 60.0)

    assert voice.list_voice_candidates() == []


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
    assert captured['headers'] == voice.LOCAL_BRIDGE_HEADERS


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
    assert captured['headers'] == voice.LOCAL_BRIDGE_HEADERS
