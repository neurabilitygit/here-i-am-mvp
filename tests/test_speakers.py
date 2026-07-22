import json

from models.schemas import SpeakerCreate
from services import speakers
from services.speakers import _auto_assign_known_speakers, _normalize_segments, apply_speaker_assignments, create_speaker, speaker_review
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
