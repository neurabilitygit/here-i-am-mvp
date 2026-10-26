from services.ollama_client import OllamaClient


def test_stage_metrics_are_separate_and_do_not_contain_prompts():
    client = OllamaClient('http://localhost', 'chat', 'analysis', 'embed')
    client._record_metrics('embedding', {'model': 'embed', 'load_duration': 2_000_000_000, 'embeddings': [[1, 2]]}, 3)
    client._record_metrics('generation', {'model': 'chat', 'eval_duration': 4_000_000_000, 'eval_count': 20, 'response': 'private'}, 5)
    assert client.last_metrics('embedding')['load_seconds'] == 2
    assert client.last_metrics('generation')['eval_seconds'] == 4
    assert client.last_metrics('generation')['load_seconds'] is None
    assert 'response' not in client.last_metrics('generation')
    assert 'embeddings' not in client.last_metrics('embedding')


def test_stage_metrics_are_thread_local():
    import threading
    client = OllamaClient('http://localhost', 'chat', 'analysis', 'embed')
    client._record_metrics('generation', {'model': 'main'}, 1)
    results = []
    thread = threading.Thread(target=lambda: results.append(client.last_metrics('generation')))
    thread.start()
    thread.join()
    assert results == [{}]
    assert client.last_metrics('generation')['model'] == 'main'


def test_evaluation_reuses_retrieval_and_defaults_to_local(monkeypatch, tmp_path, capsys):
    import json
    from types import SimpleNamespace
    from scripts import evaluate_rag
    cases = tmp_path / 'cases.jsonl'
    cases.write_text(json.dumps({'id':'case', 'question':'Where was I born?', 'reviewed':True}))
    calls = []
    def prepare(question):
        calls.append(question)
        return SimpleNamespace(mode='PERSONAL', sources=[], retrieval_seconds=.25, direct_answer=None, prompt='synthetic', evidence_text='I was born in Boston.')
    monkeypatch.setattr(evaluate_rag, 'prepare_answer', prepare)
    monkeypatch.setattr(evaluate_rag.ollama_client, 'chat', lambda prompt: 'I was born in Boston.')
    monkeypatch.setattr(evaluate_rag, 'provider_for', lambda name: (_ for _ in ()).throw(AssertionError('Cloud must not be called')))
    monkeypatch.setattr(evaluate_rag.sys, 'argv', ['evaluate_rag', str(cases), '--generate', '--require-reviewed'])
    assert evaluate_rag.main() == 0
    report = json.loads(capsys.readouterr().out)
    assert len(calls) == 1
    assert report['provider'] == 'local'
    assert report['results'][0]['retrieval_seconds'] == .25
    assert report['all_cases_reviewed'] is True


def test_release_gate_rejects_unreviewed_questions(monkeypatch, tmp_path):
    import pytest
    from scripts import evaluate_rag
    cases = tmp_path / 'cases.jsonl'
    cases.write_text('{"question":"A draft question"}')
    monkeypatch.setattr(evaluate_rag.sys, 'argv', ['evaluate_rag', str(cases), '--require-reviewed'])
    with pytest.raises(SystemExit) as result:
        evaluate_rag.main()
    assert result.value.code == 2
