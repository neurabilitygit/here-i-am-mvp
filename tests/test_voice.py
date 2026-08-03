import json

import requests

from config import settings
from models.schemas import VoiceStatus
from services.voice import _save_status, load_voice_status, public_voice_error


def _http_error(status_code: int, body: dict | None = None) -> requests.HTTPError:
    response = requests.Response()
    response.status_code = status_code
    if body is not None:
        response._content = json.dumps(body).encode('utf-8')
    return requests.HTTPError(response=response)


def test_public_voice_error_distinguishes_elevenlabs_failure_modes():
    revoked = _http_error(401)
    assert 'authenticate' in public_voice_error('elevenlabs', revoked)

    quota = _http_error(401, {'detail': {'status': 'quota_exceeded', 'message': 'no characters left'}})
    assert 'quota' in public_voice_error('elevenlabs', quota)

    rate_limited = _http_error(429)
    assert 'rate-limiting' in public_voice_error('elevenlabs', rate_limited)

    generic = _http_error(500)
    assert public_voice_error('elevenlabs', generic) == 'The ElevenLabs voice service returned an error.'

    timeout = requests.Timeout()
    assert 'too long' in public_voice_error('local', timeout)

    assert public_voice_error('local', requests.ConnectionError()) == 'Voice provider is unavailable'


def test_cloud_deletion_state_round_trips_through_status_file(tmp_path, monkeypatch):
    status_path = tmp_path / 'voice_status.json'
    monkeypatch.setattr('services.voice.STATUS_PATH', status_path)
    monkeypatch.setattr('services.voice.REFERENCE_PATH', tmp_path / 'voice_reference.wav')
    monkeypatch.setattr('services.voice.REFERENCE_TEXT_PATH', tmp_path / 'voice_reference.txt')
    monkeypatch.setattr(settings, 'voice_bridge_url', 'http://127.0.0.1:0')

    _save_status(VoiceStatus(), {
        'voice_id': 'stale-voice-id',
        'cloud_deletion_pending': True,
        'cloud_deletion_error': 'Remote voice deletion must be retried.',
    })

    reloaded = load_voice_status()
    assert reloaded.cloud_deletion_pending is True
    assert reloaded.cloud_deletion_error == 'Remote voice deletion must be retried.'
