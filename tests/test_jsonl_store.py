from services.jsonl_store import append_jsonl, recent_jsonl


def test_jsonl_rotation_preserves_history(monkeypatch, tmp_path):
    from config import settings

    monkeypatch.setattr(settings, 'jsonl_rotate_bytes', 1)
    path = tmp_path / 'activity.jsonl'
    append_jsonl(path, {'sequence': 1})
    append_jsonl(path, {'sequence': 2})

    assert [record['sequence'] for record in recent_jsonl(path, 10)] == [1, 2]
    assert len(list(tmp_path.glob('activity.*.jsonl'))) == 1
