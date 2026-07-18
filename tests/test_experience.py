import json
from pathlib import Path

from config import settings
from models.schemas import ExperiencePreferences
from services.fidelity import build_speaker_fingerprint, save_answer_feedback
from services.pipeline import direct_evidence_text, is_broad_personal_synthesis, lexical_personal_context, personal_evidence_is_sufficient, personal_retrieval_plan, route_question_without_model, voice_profile_text
from services.preferences import cloud_api_key, load_preferences, save_preferences, set_runtime_cloud_key
from services.providers import LocalProvider, OpenAIProvider, provider_for, public_provider_error, validate_provider_selection
from services.storage import create_session_dir, session_paths


def test_preferences_round_trip_without_secret_persistence():
    preferences = ExperiencePreferences(text_scale='largest', provider='openai', onboarding_complete=True)
    save_preferences(preferences)
    set_runtime_cloud_key('synthetic-secret')
    loaded = load_preferences()
    assert loaded.text_scale == 'largest'
    assert loaded.provider == 'openai'
    assert cloud_api_key() == ('synthetic-secret', 'session')
    assert 'synthetic-secret' not in Path(settings.preferences_path).read_text(encoding='utf-8')


def test_router_avoids_an_extra_model_call():
    assert route_question_without_model('What did I say about my father?') == 'PERSONAL'
    assert route_question_without_model('Explain what resilience means in my life') == 'HYBRID'
    assert route_question_without_model('What is photosynthesis?') == 'GENERAL'
    assert route_question_without_model('Where were you born?') == 'PERSONAL'
    assert route_question_without_model('Where did you grow up?') == 'PERSONAL'
    assert route_question_without_model('Who were your parents?') == 'PERSONAL'
    assert route_question_without_model('What do you remember about childhood?') == 'PERSONAL'
    assert route_question_without_model('Are you married?') == 'PERSONAL'
    assert route_question_without_model('Do you have children?') == 'PERSONAL'
    assert route_question_without_model('Can you explain photosynthesis?') == 'GENERAL'


def test_short_personal_question_expands_and_prioritizes_direct_evidence():
    query, terms, phrases = personal_retrieval_plan('Are you married?')
    evidence = direct_evidence_text(
        'Are you married?',
        [
            'My friend is married and lives nearby.',
            'I live in Massachusetts with my wife, Lisa. We have been together for many years.',
        ],
    )

    assert 'my wife' in query
    assert 'wife' in terms
    assert 'my wife' in phrases
    assert evidence.splitlines()[0].startswith('- I live in Massachusetts with my wife, Lisa.')
    assert 'My friend is married' not in evidence


def test_lexical_personal_context_prefers_speakers_relationship(tmp_path, monkeypatch):
    session_dir = tmp_path / 'session-one'
    session_dir.mkdir()
    records = [
        {
            'text': 'My friend is married and his wife lives nearby.',
            'metadata': {'session_id': 'session-one', 'chunk_index': 0},
        },
        {
            'text': 'I live in Massachusetts with my wife, Lisa.',
            'metadata': {'session_id': 'session-one', 'chunk_index': 1},
        },
    ]
    (session_dir / 'chunks.jsonl').write_text(
        '\n'.join(json.dumps(record) for record in records),
        encoding='utf-8',
    )
    (session_dir / 'processing_state.json').write_text(
        json.dumps({'embedded': True, 'active_content_version': None}),
        encoding='utf-8',
    )
    monkeypatch.setattr('services.pipeline.list_session_dirs', lambda: [session_dir])

    docs, metas, distances = lexical_personal_context('Are you married?')

    assert docs == ['I live in Massachusetts with my wife, Lisa.']
    assert metas[0]['chunk_index'] == 1
    assert distances[0] < 0


def test_evidence_gate_accepts_direct_fact_and_rejects_unrelated_results():
    assert personal_evidence_is_sufficient(
        'Are you married?',
        ['I live in Massachusetts with my wife, Lisa.'],
        [{'title': 'Home'}],
        [-13.0],
    )
    assert not personal_evidence_is_sufficient(
        'What was your first car?',
        ['I remember playing handball during school recess.'],
        [{'title': 'Childhood games', 'topics': 'school, friends'}],
        [1.34],
    )


def test_evidence_gate_allows_close_semantic_result_with_term_overlap():
    assert personal_evidence_is_sufficient(
        'What is your favorite color?',
        ['This is a recording test. My favorite color is blue.'],
        [{'title': 'Recording test'}],
        [1.08],
    )


def test_broad_personal_synthesis_uses_available_memories_without_literal_overlap():
    question = 'What are some interesting things to know about me?'
    query, terms, _phrases = personal_retrieval_plan(question)

    assert is_broad_personal_synthesis(question)
    assert route_question_without_model(question) == 'PERSONAL'
    assert 'first-person autobiography' in query
    assert 'family' in terms
    assert personal_evidence_is_sufficient(
        question,
        ['I grew up in New York and later built a career and family.'],
        [{'title': 'A life story'}],
        [1.55],
    )


def test_personal_question_stays_personal_when_retrieval_is_empty(monkeypatch):
    from services.pipeline import prepare_answer

    monkeypatch.setattr('services.pipeline.query_context_with_distances', lambda _question: ([], [], []))
    monkeypatch.setattr('services.pipeline.fingerprint_prompt', lambda: 'Synthetic fingerprint')
    monkeypatch.setattr('services.pipeline.voice_profile_text', lambda: '')

    prepared = prepare_answer('Where were you born?')

    assert prepared.mode == 'PERSONAL'
    assert prepared.sources == []
    assert prepared.prompt == ''
    assert prepared.direct_answer == "I don't know the answer based on what I've recorded."


def test_supported_personal_question_still_builds_grounded_prompt(monkeypatch):
    from services.pipeline import prepare_answer

    monkeypatch.setattr(
        'services.pipeline.query_context_with_distances',
        lambda _question: (
            ['I was born in the Bronx, New York.'],
            [{'session_id': 'one', 'chunk_index': 0}],
            [0.9],
        ),
    )
    monkeypatch.setattr('services.pipeline.lexical_personal_context', lambda _question, limit=2: ([], [], []))
    monkeypatch.setattr('services.pipeline.fingerprint_prompt', lambda: 'Synthetic fingerprint')
    monkeypatch.setattr('services.pipeline.voice_profile_text', lambda: '')

    prepared = prepare_answer('Where were you born?')

    assert prepared.direct_answer is None
    assert 'recorded individual' in prepared.prompt
    assert 'never to the AI model' in prepared.prompt
    assert prepared.prompt.index('QUESTION') < prepared.prompt.index('SPEAKER_FINGERPRINT')


def test_direct_personal_fact_prompt_rejects_unrelated_anecdotes(monkeypatch):
    from services.pipeline import prepare_answer

    monkeypatch.setattr(
        'services.pipeline.query_context_with_distances',
        lambda _question: (
            ['I live with my wife, Lisa. My friend is also married.'],
            [{'session_id': 'one', 'chunk_index': 0}],
            [0.2],
        ),
    )
    monkeypatch.setattr('services.pipeline.lexical_personal_context', lambda _question, limit=2: ([], [], []))
    monkeypatch.setattr('services.pipeline.fingerprint_prompt', lambda: 'Synthetic fingerprint')
    monkeypatch.setattr('services.pipeline.voice_profile_text', lambda: '')

    prepared = prepare_answer('Are you married?')

    assert 'exactly one sentence' in prepared.prompt
    assert 'beginning with Yes or No' in prepared.prompt


def test_provider_selection_and_gpt5_payload_hold_retrieval_constant():
    set_runtime_cloud_key('synthetic-secret')
    assert provider_for('local').name == 'local'
    provider = OpenAIProvider('gpt-5.4-mini')
    payload = provider._payload('grounded prompt', stream=False)
    assert payload['model'] == 'gpt-5.4-mini'
    assert payload['input'] == 'grounded prompt'
    assert payload['store'] is False
    assert 'temperature' not in payload


def test_local_provider_expands_only_narrative_personal_prompts():
    narrative = 'QUESTION\nTell me a story.\n\nRESPONSE_KIND\nNARRATIVE_PERSONAL'
    direct = 'QUESTION\nAre you married?\n\nRESPONSE_KIND\nDIRECT_PERSONAL'

    expanded = LocalProvider._prompt(narrative)

    assert 'target 120 to 160 words' in expanded
    assert 'at least three distinct relevant facts or memories' in expanded
    assert LocalProvider._prompt(direct) == direct
    assert OpenAIProvider('gpt-5.4-mini')._payload(narrative, stream=False)['input'] == narrative


def test_provider_selection_rejects_unapproved_cloud_model():
    set_runtime_cloud_key('synthetic-secret')
    preferences = ExperiencePreferences(provider='openai', cloud_model='unapproved-model')
    try:
        validate_provider_selection(preferences)
    except RuntimeError as exc:
        assert 'not approved' in str(exc)
    else:
        raise AssertionError('Unapproved cloud model was accepted')


def test_provider_errors_are_safe_for_the_browser():
    error = RuntimeError('secret upstream details')
    message = public_provider_error('openai', error)
    assert 'secret upstream details' not in message
    assert 'setting was not changed' in message


def test_legacy_voice_profile_is_bounded_for_interactive_latency(monkeypatch):
    repeated = ['A detailed observation about speaking style.'] * 100
    monkeypatch.setattr('services.pipeline.load_voice_profile', lambda: {
        'sentence_rhythm': repeated,
        'vocabulary_style': repeated,
        'rhetorical_habits': repeated,
        'pacing_style': repeated,
        'humor_style': repeated,
        'storytelling_style': repeated,
        'conversational_stance': repeated,
        'prosody_notes': repeated,
        'style_exemplars': repeated,
    })
    text = voice_profile_text()
    assert len(text) <= 2200
    assert text.count('A detailed observation') == 10


def test_fingerprint_uses_reviewed_transcripts():
    _session_id, session = create_session_dir('fingerprint')
    session_paths(session)['transcript'].write_text(
        '# Transcript\n\nI remember that summer. You know, I think about that summer often. '
        'I remember the long afternoons. I think those afternoons changed me.\n',
        encoding='utf-8',
    )
    fingerprint = build_speaker_fingerprint()
    assert fingerprint.transcript_count >= 1
    assert fingerprint.word_count > 10
    assert fingerprint.average_sentence_words > 0
    assert Path(settings.fidelity_profile_path).exists()


def test_feedback_is_append_only_jsonl():
    from models.schemas import AnswerFeedback

    feedback = AnswerFeedback(
        question='A synthetic question', answer='A synthetic answer', rating='up',
        reason='sounds_like_me', mode='PERSONAL', provider='local',
    )
    save_answer_feedback(feedback)
    save_answer_feedback(feedback)
    lines = Path(settings.feedback_path).read_text(encoding='utf-8').splitlines()
    assert len(lines) == 2
    assert all(json.loads(line)['rating'] == 'up' for line in lines)
