from services.pipeline import build_chunk_records, metadata_prompt, normalize_chroma_value, semantic_chunks


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
