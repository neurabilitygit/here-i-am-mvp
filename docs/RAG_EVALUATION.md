# Memoir RAG quality gate

`scripts/evaluate_rag.py` is a read-only evaluation runner. Copy
`evals/memoir_rag.example.jsonl`, replace the synthetic session identifiers,
and add reviewed questions covering direct facts, paraphrases, broad synthesis,
unknown facts, conflicting memories, names, dates, interviewer-leading
questions, sealed memories, archived memories, and transcript prompt injection.

Run retrieval-only evaluation first:

```bash
PYTHONPATH=app python scripts/evaluate_rag.py evals/memoir_rag.jsonl
```

Use `--generate` only when the selected answer provider is intentionally ready.
The report contains identifiers, ranks, abstention results, and character counts;
it does not write answers or transcript text to disk.

Release targets:

- retrieval recall at the configured context limit: at least 90%
- supported personal claims: at least 98%
- unknown-answer precision and recall: at least 90%
- speaker attribution after human review: 100% in the reviewed gold set

Do not tune retrieval weights, distance thresholds, routing phrases, or models
without saving a before-and-after report from the same reviewed case set.
