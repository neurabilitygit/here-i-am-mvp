from services.pipeline import (
    build_chunk_records,
    build_conversation_chunk_records,
    active_chroma_filter,
    content_version_for,
    metadata_prompt,
    normalize_chroma_value,
    record_is_active,
    semantic_chunks,
    subject_evidence_only,
)


def test_semantic_chunks_do_not_cut_words_and_overlap():
    text = ' '.join(f'word{i}' for i in range(30))
    chunks = semantic_chunks(text, max_words=10, overlap_words=2)
    assert len(chunks) >= 3
    assert all(len(chunk.split()) <= 10 for chunk in chunks)
    assert chunks[0].split()[-2:] == chunks[1].split()[:2]


def test_metadata_prompt_keeps_supplied_material():
    marker = 'END_OF_TRANSCRIPT_MARKER'
    prompt = metadata_prompt('session', ('memory ' * 6000) + marker)
    assert marker in prompt


def test_chroma_metadata_normalization():
    assert normalize_chroma_value(['a', 'b']) == 'a, b'
    assert normalize_chroma_value(None) == ''


def test_chunk_records_have_deterministic_ids_and_schema_version():
    records = build_chunk_records(
        'session-1',
        'A short memory about a summer afternoon.',
        {'title': 'Summer', 'summary': 'A memory', 'topics': ['summer']},
    )
    assert records[0]['id'] == 'session-1::chunk::0000'
    assert records[0]['metadata']['session_id'] == 'session-1'
    assert records[0]['metadata']['schema_version'] == '2.0'


def test_versioned_chunk_ids_are_append_only_and_retrieval_uses_manifest():
    transcript = 'A short memory about a summer afternoon.'
    version = content_version_for(transcript)
    records = build_chunk_records(
        'session-1',
        transcript,
        {'title': 'Summer', 'summary': 'A memory', 'topics': ['summer']},
        content_version=version,
    )
    assert records[0]['id'] == f'session-1::version::{version}::chunk::0000'
    assert record_is_active(records[0]['metadata'], {'session-1': version}) is True
    assert record_is_active(records[0]['metadata'], {'session-1': 'newer-version'}) is False
    assert record_is_active(records[0]['metadata'], {}) is False


def test_active_chroma_filter_uses_versioned_manifest_and_preserves_legacy_fallback():
    assert active_chroma_filter({'old': 'legacy'}) is None
    assert active_chroma_filter({}) is None
    where = active_chroma_filter({'session-1': 'version-a'})
    assert where == {
        '$and': [
            {'session_id': {'$eq': 'session-1'}},
            {'content_version': {'$eq': 'version-a'}},
        ],
    }


def test_conversation_chunks_mark_subject_evidence_and_keep_questions_context_only():
    records = build_conversation_chunk_records(
        'conversation-1',
        [{
            'memory_unit_id': 'unit-0001',
            'subject_speaker_id': 'eric',
            'subject_evidence': 'I built a tree house with my father.',
            'retrieval_context': 'What did you build as a child?',
            'start': 2.0,
            'end': 7.0,
        }],
        {'title': 'Childhood', 'summary': 'A childhood memory'},
        content_version='version-a',
    )

    assert records[0]['metadata']['evidence_role'] == 'memory_subject'
    assert records[0]['metadata']['subject_speaker_id'] == 'eric'
    assert 'retrieval only, not autobiographical evidence' in records[0]['text']
    assert 'Memory subject evidence: I built a tree house' in records[0]['text']
    assert subject_evidence_only(records[0]['text']) == 'I built a tree house with my father.'
