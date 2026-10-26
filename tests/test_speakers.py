import json

from models.schemas import SpeakerCreate
from services import speakers
from services.speakers import _auto_assign_known_speakers, _known_speaker_references, _normalize_segments, apply_speaker_assignments, create_speaker, get_speaker_record, revise_conversation_transcript, revoke_speaker_voice_reference, speaker_review, update_speaker_record
from services.storage import create_session_dir, load_json, save_json, session_paths, update_processing_state


def test_speaker_assignment_creates_subject_only_memory_units():
    interviewer = create_speaker(SpeakerCreate(display_name='Pat Interviewer', default_role='interviewer'))
    session_id, session = create_session_dir('A two person memory')
    paths = session_paths(session)
    turns = [
        {'cluster_id': 'voice-a', 'start': 0.0, 'end': 1.0, 'text': 'Where did you grow up?'},
        {'cluster_id': 'voice-b', 'start': 1.1, 'end': 2.0, 'text': 'I grew up in New York.'},
    ]
    save_json(paths['transcript_turns'], {'schema_version': 1, 'turns': turns})
    update_processing_state(
        session,
        recording_mode='conversation',
        transcribed=True,
        speaker_review_status='needs_review',
    )

    result = apply_speaker_assignments(session, [
        {
            'cluster_id': 'voice-a',
            'speaker_id': interviewer.speaker_id,
            'display_name': None,
            'role': 'interviewer',
        },
        {
            'cluster_id': 'voice-b',
            'speaker_id': None,
            'display_name': 'Eric Subject',
            'role': 'memory_subject',
        },
    ])

    units = [json.loads(line) for line in paths['memory_units'].read_text(encoding='utf-8').splitlines()]
    assert result['session_id'] == session_id
    assert result['memory_unit_count'] == 1
    assert units[0]['subject_evidence'] == 'I grew up in New York.'
    assert units[0]['retrieval_context'] == 'Where did you grow up?'
    assert 'Where did you grow up?' not in units[0]['subject_evidence']
    state = load_json(paths['state'])
    assert state['speaker_review_status'] == 'complete'
    assert state['embedded'] is False


def test_speaker_review_exposes_each_detected_voice_without_embedding():
    _session_id, session = create_session_dir('Review voices')
    paths = session_paths(session)
    save_json(paths['transcript_turns'], {'schema_version': 1, 'turns': [
        {'cluster_id': 'voice-a', 'start': 0.0, 'end': 3.0, 'text': 'Tell me about your first home.'},
        {'cluster_id': 'voice-b', 'start': 3.0, 'end': 8.0, 'text': 'My first home was in the Bronx.'},
    ]})
    update_processing_state(session, recording_mode='conversation', speaker_review_status='needs_review')

    review = speaker_review(session)

    assert review['status'] == 'needs_review'
    assert [cluster['cluster_id'] for cluster in review['clusters']] == ['voice-a', 'voice-b']
    assert all('/speaker-samples/' in cluster['sample_url'] for cluster in review['clusters'])


def test_diarization_segments_merge_adjacent_turns_without_losing_speaker_labels():
    turns = _normalize_segments({'segments': [
        {'speaker': 'speaker_0', 'start': 0.0, 'end': 1.0, 'text': 'First question.'},
        {'speaker': 'speaker_0', 'start': 1.1, 'end': 2.0, 'text': 'More detail.'},
        {'speaker': 'speaker_1', 'start': 2.1, 'end': 4.0, 'text': 'The answer.'},
    ]})

    assert len(turns) == 2
    assert turns[0]['cluster_id'] == 'speaker_0'
    assert turns[0]['text'] == 'First question. More detail.'
    assert turns[1]['cluster_id'] == 'speaker_1'


def test_known_speaker_labels_still_require_identity_confidence(monkeypatch):
    subject = create_speaker(SpeakerCreate(display_name='Known Subject', default_role='memory_subject'))
    interviewer = create_speaker(SpeakerCreate(display_name='Known Interviewer', default_role='interviewer'))
    _session_id, session = create_session_dir('Known voices')
    applied = []
    monkeypatch.setattr(speakers, 'apply_speaker_assignments', lambda *_args: applied.append(True))
    turns = [
        {'cluster_id': subject.speaker_id, 'start': 0.0, 'end': 2.0, 'text': 'A memory.'},
        {'cluster_id': interviewer.speaker_id, 'start': 2.0, 'end': 3.0, 'text': 'A question.'},
    ]

    assert _auto_assign_known_speakers(session, turns) is False
    assert applied == []

    confident = [{**turn, 'speaker_confidence': 0.97} for turn in turns]
    assert _auto_assign_known_speakers(session, confident) is True
    assert applied == [True]


def test_speaker_assignment_retry_does_not_create_a_second_identity():
    _session_id, session = create_session_dir('Retry-safe voices')
    paths = session_paths(session)
    save_json(paths['transcript_turns'], {'schema_version': 1, 'turns': [
        {'cluster_id': 'questioner', 'start': 0.0, 'end': 1.0, 'text': 'Where was home?'},
        {'cluster_id': 'subject', 'start': 1.0, 'end': 3.0, 'text': 'Home was Albany.'},
    ]})
    payload = [
        {'cluster_id': 'questioner', 'display_name': 'Retry Interviewer', 'role': 'interviewer'},
        {'cluster_id': 'subject', 'display_name': 'Retry Subject', 'role': 'memory_subject'},
    ]

    first = apply_speaker_assignments(session, payload)
    second = apply_speaker_assignments(session, payload)

    assert [item['speaker_id'] for item in second['assignments']] == [item['speaker_id'] for item in first['assignments']]


def test_reviewed_conversation_words_can_be_revised_with_prior_version_preserved():
    interviewer = create_speaker(SpeakerCreate(display_name='Revision Interviewer', default_role='interviewer'))
    subject = create_speaker(SpeakerCreate(display_name='Revision Subject', default_role='memory_subject'))
    _session_id, session = create_session_dir('Editable conversation')
    paths = session_paths(session)
    save_json(paths['transcript_turns'], {'schema_version': 1, 'turns': [
        {'cluster_id': 'a', 'start': 0.0, 'end': 1.0, 'text': 'Where was home?'},
        {'cluster_id': 'b', 'start': 1.0, 'end': 3.0, 'text': 'Home was Albeny.'},
    ]})
    assignments = [
        {'cluster_id': 'a', 'speaker_id': interviewer.speaker_id, 'role': 'interviewer'},
        {'cluster_id': 'b', 'speaker_id': subject.speaker_id, 'role': 'memory_subject'},
    ]
    apply_speaker_assignments(session, assignments)
    original = paths['transcript'].read_text(encoding='utf-8')

    result = revise_conversation_transcript(
        session,
        '**Revision Interviewer:** Where was home?\n\n**Revision Subject:** Home was Albany.',
        'corrected place name',
    )

    assert result['memory_unit_count'] == 1
    assert 'Home was Albany.' in paths['transcript'].read_text(encoding='utf-8')
    revision = session / 'conversation.revisions' / result['revision_id'] / 'transcript.md'
    assert revision.read_text(encoding='utf-8') == original
    units = [json.loads(line) for line in paths['memory_units'].read_text(encoding='utf-8').splitlines()]
    assert units[0]['subject_evidence'] == 'Home was Albany.'


def test_voice_reference_requires_consent_and_revocation_removes_it(tmp_path):
    speaker = create_speaker(SpeakerCreate(display_name='Consent Test Speaker'))
    reference = tmp_path / 'voice-reference.wav'
    reference.write_bytes(b'RIFF-consented-reference')
    update_speaker_record(speaker.speaker_id, voice_reference_path=str(reference))

    assert _known_speaker_references() == []

    update_speaker_record(speaker.speaker_id, voice_reference_consent={
        'consented': True,
        'consented_at': '2026-01-01T00:00:00+00:00',
        'revoked_at': None,
        'disclosure_version': '1.0',
    })
    references = _known_speaker_references()
    assert any(name == speaker.speaker_id for name, _value in references)

    profile = revoke_speaker_voice_reference(speaker.speaker_id)
    assert profile.voice_matching_consented is False
    assert not reference.exists()
    assert get_speaker_record(speaker.speaker_id)['voice_reference_path'] is None
