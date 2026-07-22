from pathlib import Path


def test_chroma_is_append_only():
    root = Path(__file__).parents[1]
    sources = '\n'.join(
        path.read_text(encoding='utf-8')
        for base in (root / 'app', root / 'scripts')
        for path in base.rglob('*.py')
        if '__pycache__' not in path.parts and not path.name.startswith('._')
    )
    assert 'collection.delete(' not in sources
    assert 'target.delete(' not in sources
    assert '.delete(where' not in sources


def test_native_bridges_are_detached_and_read_the_protected_token():
    root = Path(__file__).parents[1]
    launcher = (root / 'scripts' / 'start.sh').read_text()
    runner = (root / 'scripts' / 'run_native_bridge.sh').read_text()
    daemonizer = (root / 'scripts' / 'daemonize.py').read_text()
    assert 'scripts/daemonize.py' in launcher
    assert 'nohup "$SOURCE_DIR/scripts/start_voice.sh"' not in launcher
    assert 'os.setsid()' in daemonizer
    assert daemonizer.count('os.fork()') == 2
    assert 'local_bridge_token' in runner
    assert 'exec "$SOURCE_DIR/scripts/start_voice.sh"' in runner


def test_voice_environment_is_built_at_its_final_absolute_path():
    root = Path(__file__).parents[1]
    launcher = (root / 'scripts' / 'start_voice.sh').read_text(encoding='utf-8')

    assert 'python3.12 -m venv "$ENV_DIR"' in launcher
    assert 'mv "$NEXT_ENV" "$ENV_DIR"' not in launcher
    assert 'restore_previous_env' in launcher


def test_native_mutation_bridges_require_an_explicit_auth_probe():
    root = Path(__file__).parents[1]
    launcher = (root / 'scripts' / 'start.sh').read_text(encoding='utf-8')
    for name in ('mlx_voice_bridge.py', 'ollama_control_bridge.py'):
        bridge = (root / 'scripts' / name).read_text(encoding='utf-8')
        assert "@app.post('/auth/check')" in bridge
        assert "request.method != 'GET'" in bridge
        assert "X-Here-I-Am-Local" in bridge
        assert "'build_commit': APP_BUILD_COMMIT" in bridge
    assert '"$url/auth/check"' in launcher
    assert 'bridge_build_matches' in launcher


def test_frontend_ignores_stale_chat_completions_and_batches_screen_reader_updates():
    root = Path(__file__).parents[1]
    script = (root / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    core = (root / 'app' / 'static' / 'app-core.js').read_text(encoding='utf-8')
    template = (root / 'app' / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert 'chatGeneration' in core
    assert core.lstrip().startswith('(() => {')
    assert 'generation !== state.chatGeneration' in script
    assert 'answer-announcement' in template
    assert 'id="answer-text" class="answer-text" aria-live=' not in template
    assert template.index('/static/app-core.js') < template.index('/static/app.js')


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


def test_voice_completion_is_bound_to_the_answer_that_requested_it():
    root = Path(__file__).parents[1]
    script = (root / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    core = (root / 'app' / 'static' / 'app-core.js').read_text(encoding='utf-8')

    assert "if (state.voicePreparing || state.voicePlaying) stopSpeaking();" in script
    assert 'state.chatGeneration !== answerGeneration' in script
    assert 'state.lastAnswer !== answerText' in script
    assert "voice_prepare_discarded" in script
    assert 'voiceGeneration' in core


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


def test_background_recording_completion_does_not_steal_the_talk_scene():
    root = Path(__file__).parents[1]
    script = (root / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')

    assert "const sceneAtCompletion = document.body.dataset.scene || ''" in script
    assert "if (sceneAtCompletion === 'remember') showScene('memories', 'recording_upload_completed')" in script
    assert "showScene('memories');" not in script


def test_answer_state_and_privacy_safe_activity_are_recoverable():
    root = Path(__file__).parents[1]
    script = (root / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    core = (root / 'app' / 'static' / 'app-core.js').read_text(encoding='utf-8')

    assert "const ANSWER_STORAGE_KEY = 'here-i-am.current-answer.v1'" in script
    assert 'persistCompletedAnswer();' in script
    assert 'restoreCompletedAnswer()' in script
    assert "activity('scene_changed'" in script
    assert "activity('answer_completed'" in script
    assert "activity('voice_prepare_failed'" in script
    assert "fetch('/api/activity-events'" in core


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


def test_answer_close_control_clears_the_complete_talk_state():
    root = Path(__file__).parents[1]
    script = (root / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    template = (root / 'app' / 'templates' / 'index.html').read_text(encoding='utf-8')
    assert 'id="clear-answer"' in template
    assert 'aria-label="Clear this answer"' in template
    assert "byId('clear-answer').addEventListener('click',clearAnswer)" in script
    assert 'function clearAnswer()' in script
    clear_body = script.split('function clearAnswer()', 1)[1].split('\n}', 1)[0]
    assert 'state.chatAbort?.abort()' in clear_body
    assert 'cancelVoicePrerender()' in clear_body
    assert "byId('answer-text').textContent = ''" in clear_body
    assert "byId('answer-card').hidden = true" in clear_body
    assert "state.lastAnswer = ''" in clear_body
    assert 'renderTalkProviderBadge(state.preferences?.provider)' in clear_body


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
    assert "onlyReview?'Name voices first'" in script
    assert "failed?'Try again':'Prepare all memories'" in script
    assert 'Nothing was lost, and it is safe to try again.' in script
    assert "byId('library-status').textContent=outcome" in script


def test_conversation_recording_has_voice_review_and_per_speaker_avatar_controls():
    root = Path(__file__).parents[1]
    script = (root / 'app' / 'static' / 'app.js').read_text(encoding='utf-8')
    template = (root / 'app' / 'templates' / 'index.html').read_text(encoding='utf-8')

    assert 'id="record-mode-conversation"' in template
    assert 'id="import-mode-conversation"' in template
    assert 'id="speaker-review-dialog"' in template
    assert 'id="speaker-avatar-dialog"' in template
    assert 'id="speaker-photo-consent"' in template
    assert "form.append('recording_mode'" in script
    assert '/speaker-assignments' in script
    assert '/avatar/generate' in script
