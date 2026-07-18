from pathlib import Path
from types import SimpleNamespace
from io import BytesIO

import numpy as np
import pytest
import soundfile as sf
from fastapi import HTTPException

from scripts import mlx_voice_bridge as bridge


def test_sentence_foundry_preserves_words_and_bounds_segments():
    text = (
        'This first sentence contains enough natural words to establish a calm and recognizable speaking rhythm for the listener. '
        'The second sentence adds another idea, with a comma, so the segmenter has a graceful place to divide a longer thought. '
        'This ending is short.'
    )
    segments = bridge.sentence_segments(text)

    assert ' '.join(' '.join(segments).split()) == ' '.join(text.split())
    assert len(segments) >= 2
    assert all(len(segment.split()) >= 15 for segment in segments)
    assert all(len(segment.split()) <= 30 for segment in segments)
    assert all(90 <= bridge.adaptive_token_ceiling(segment) <= 480 for segment in segments)


def test_sentence_foundry_rebalances_a_short_tail():
    text = ' '.join(f'word{index}' for index in range(35))

    segments = bridge.sentence_segments(text)

    assert [len(segment.split()) for segment in segments] == [20, 15]


def test_segment_cleanup_trims_quiet_edges_and_applies_fades():
    audio = np.concatenate((
        np.full(1200, .0005, dtype=np.float32),
        np.full(2400, .2, dtype=np.float32),
        np.full(1200, .0005, dtype=np.float32),
    ))

    cleaned = bridge.trim_segment_artifacts(audio, 24000)

    assert cleaned.size < audio.size
    assert abs(cleaned[0]) < 1e-6
    assert abs(cleaned[-1]) < 1e-6
    assert np.max(cleaned) > .19


def test_stitching_adds_faded_pause_and_applies_speed():
    first = np.ones(2400, dtype=np.float32)
    second = np.ones(2400, dtype=np.float32)

    normal = bridge.stitch_audio([first, second], 24000, speed=1.0)
    faster = bridge.stitch_audio([first, second], 24000, speed=1.2)

    assert normal.size == 2400 + 1800 + 2400
    assert faster.size == int(normal.size / 1.2)
    assert np.allclose(normal[2400:4200], 0)


def test_synthesis_batches_and_reuses_cached_wav(monkeypatch, tmp_path):
    reference = tmp_path / 'reference.wav'
    sf.write(reference, np.zeros(24000, dtype=np.float32), 24000)
    monkeypatch.setenv('QWEN_TTS_CACHE_DIR', str(tmp_path / 'cache'))
    calls = []

    class FakeModel:
        sample_rate = 24000

        def batch_generate(self, texts, **kwargs):
            calls.append((list(texts), kwargs['max_tokens']))
            for index, _text in enumerate(texts):
                yield SimpleNamespace(
                    audio=np.full(1200, .1, dtype=np.float32),
                    sequence_idx=index,
                    sample_rate=24000,
                )

    monkeypatch.setattr(bridge, 'load_model', lambda: FakeModel())
    monkeypatch.setattr(bridge, 'cached_reference_audio', lambda *_args: object())
    request = bridge.SynthesisRequest(
        text=' '.join(['A bounded sentence with a recognizable speaking cadence for local testing.'] * 8),
        reference_audio=str(reference),
        reference_text='Reference words for the same speaker.',
        request_id='foundry-test',
    )

    first = bridge.synthesize(request)
    second = bridge.synthesize(request)

    assert first.headers['x-voice-cache'] == 'miss'
    assert second.headers['x-voice-cache'] == 'hit'
    assert first.headers['x-voice-segments'] == str(len(bridge.sentence_segments(request.text)))
    assert len(calls) >= 1
    assert all(len(texts) <= bridge.SENTENCE_BATCH_SIZE for texts, _ceiling in calls)


def test_timed_out_synthesis_resumes_cached_segments_and_stitches_one_wav(monkeypatch, tmp_path):
    reference = tmp_path / 'reference.wav'
    sf.write(reference, np.zeros(24000, dtype=np.float32), 24000)
    monkeypatch.setenv('QWEN_TTS_CACHE_DIR', str(tmp_path / 'cache'))
    monkeypatch.setattr(bridge, 'SENTENCE_BATCH_SIZE', 2)
    calls = []

    class TimeoutThenResumeModel:
        sample_rate = 24000

        def batch_generate(self, texts, **_kwargs):
            calls.append(list(texts))
            if len(calls) == 2:
                raise HTTPException(status_code=504, detail='synthetic watchdog')
            for index, _text in enumerate(texts):
                yield SimpleNamespace(
                    audio=np.full(1200, .1 + len(calls) * .01, dtype=np.float32),
                    sequence_idx=index,
                    sample_rate=24000,
                )

    model = TimeoutThenResumeModel()
    monkeypatch.setattr(bridge, 'load_model', lambda: model)
    monkeypatch.setattr(bridge, 'cached_reference_audio', lambda *_args: object())
    sentences = [
        f'Segment {index} contains enough carefully chosen words to remain separate and produce a useful cached voice checkpoint.'
        for index in range(4)
    ]
    request = bridge.SynthesisRequest(
        text=' '.join(sentences),
        reference_audio=str(reference),
        reference_text='Reference words for the same speaker.',
        request_id='resume-test',
    )

    with pytest.raises(HTTPException) as failure:
        bridge.synthesize(request)
    assert failure.value.status_code == 504

    key = bridge.cache_key(request)
    segment_directory = bridge.segment_cache_dir(request, key)
    assert bridge.segment_cache_path(segment_directory, 0).exists()
    assert bridge.segment_cache_path(segment_directory, 1).exists()
    assert not bridge.segment_cache_path(segment_directory, 2).exists()
    assert (segment_directory / '.retry-single').exists()

    response = bridge.synthesize(request.model_copy(update={'request_id': 'resume-test-2'}))
    audio, sample_rate = sf.read(BytesIO(response.body), dtype='float32')

    assert response.headers['x-voice-segments-resumed'] == '2'
    assert response.headers['x-voice-segment-cache'] == 'hit'
    assert response.headers['x-voice-batch-size'] == '1'
    assert calls[2:] == [[sentences[2]], [sentences[3]]]
    assert sample_rate == 24000
    assert audio.size == (4 * 1200) + (3 * 1800)
    assert bridge.cache_path(request, key).exists()
    assert not (segment_directory / '.retry-single').exists()


def test_segment_cache_key_invalidates_when_text_or_reference_changes(tmp_path):
    reference = tmp_path / 'reference.wav'
    sf.write(reference, np.zeros(24000, dtype=np.float32), 24000)
    request = bridge.SynthesisRequest(text='The original answer.', reference_audio=str(reference))

    original = bridge.cache_key(request)
    changed_text = bridge.cache_key(request.model_copy(update={'text': 'A changed answer.'}))
    stat = reference.stat()
    reference.touch()
    if reference.stat().st_mtime_ns == stat.st_mtime_ns:
        reference.write_bytes(reference.read_bytes() + b'\0')
    changed_reference = bridge.cache_key(request)

    assert changed_text != original
    assert changed_reference != original
