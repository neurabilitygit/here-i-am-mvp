from pathlib import Path


def test_background_voice_is_single_flight_in_the_browser():
    root = Path(__file__).parents[1]
    script_path = root / 'app' / 'static' / 'app.js'
    if not script_path.exists():
        script_path = root / 'static' / 'app.js'
    script = script_path.read_text(encoding='utf-8')

    assert 'Your voice file is already being prepared' in script
    assert 'A voice file is already being prepared. Please wait for it to finish.' in script
    assert 'Finishing an earlier voice attempt — this one will start next' not in script
    assert "label.textContent = preparing ? 'Preparing' : ready ? 'Ready—Play' : 'Play'" in script


def test_completed_voice_uses_unlocked_web_audio_and_explicit_states():
    root = Path(__file__).parents[1]
    script_path = root / 'app' / 'static' / 'app.js'
    if not script_path.exists():
        script_path = root / 'static' / 'app.js'
    script = script_path.read_text(encoding='utf-8')

    assert 'decodeAudioData' in script
    assert 'createBufferSource' in script
    assert 'state.audio.play()' not in script
    assert "'Preparing'" in script
    assert "'Ready—Play'" in script
    assert "textContent = 'Playing'" in script


def test_safari_recording_waits_for_the_final_audio_blob():
    root = Path(__file__).parents[1]
    script_path = root / 'app' / 'static' / 'app.js'
    if not script_path.exists():
        script_path = root / 'static' / 'app.js'
    script = script_path.read_text(encoding='utf-8')

    assert "const candidates=isSafari?['audio/mp4'" in script
    assert 'state.mediaRecorder.onstop=finalizeRecording' in script
    assert 'state.mediaRecorder.stop(); state.mediaStream?.getTracks()' not in script
    assert 'await uploadRecording({unexpected})' in script
    assert "The microphone stopped. Saving everything captured so far" in script


def test_talk_card_does_not_render_memory_source_chips():
    root = Path(__file__).parents[1]
    script_path = root / 'app' / 'static' / 'app.js'
    template_path = root / 'app' / 'templates' / 'index.html'
    if not script_path.exists():
        script_path = root / 'static' / 'app.js'
        template_path = root / 'templates' / 'index.html'

    script = script_path.read_text(encoding='utf-8')
    template = template_path.read_text(encoding='utf-8')

    assert 'answer-sources' not in script
    assert 'answer-sources' not in template
    assert 'Memories used' not in template


def test_memories_page_supports_accessible_audio_file_import():
    root = Path(__file__).parents[1]
    script = (root / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    template = (root / 'app' / 'templates' / 'index.html').read_text(encoding='utf-8')

    assert 'id="memory-import"' in template
    assert 'id="memory-upload-input"' in template
    assert 'accept="audio/*' in template
    assert 'multiple' in template
    assert "zone.addEventListener('drop'" in script
    assert "input.addEventListener('change'" in script
    assert "await api('/api/recordings/upload'" in script
    assert 'refreshMemoryQueue()' in script


def test_memory_batch_failure_remains_visible_and_retryable():
    root = Path(__file__).parents[1]
    script = (root / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    template = (root / 'app' / 'templates' / 'index.html').read_text(encoding='utf-8')

    assert 'id="memory-queue-error"' in template
    assert "queue.last_job?.status==='error'" in script
    assert "failed?'Try again':'Prepare all memories'" in script
    assert 'Nothing was lost, and it is safe to try again.' in script
    assert "byId('library-status').textContent=outcome" in script
