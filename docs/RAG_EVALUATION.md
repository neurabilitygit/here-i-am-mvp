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

## Reproducible local baseline

`scripts/baseline_inventory.py --candidate <checkout> --deployed-source <checkout>
--sample <audio>` hashes scoped source files and selected audio without opening
Chroma. Keep personal reports/cases under ignored `reports/private/` and
`evals/private/`, not in GitHub.

`--generate` now defaults to local generation regardless of the UI preference.
Cloud generation requires `--provider openai`. Evaluation retrieves once per
question and reports retrieval separately from generation, with local model
load/prompt/decode timings when available. Missing metrics are null, not zero.
Timing fields follow the official [generation API](https://docs.ollama.com/api/generate)
and [embedding API](https://docs.ollama.com/api/embed). Voice preparation is
measured separately with `scripts/benchmark_voice_models.py`.

Use `--require-reviewed` for a release gate. Approval of the sample recordings
is not confirmation of transcript accuracy. The user approved the initial two
recordings on 2026-10-26; names, dates, and expected answers still need review.

`scripts/benchmark_embedding_lifecycle.py --confirm-idle` compares current
unload-after-query behavior with short residency using synthetic text. Run only
when chat/indexing are idle. It releases the tested embedding model afterward,
without changing vectors or preferences. Report cold and warm runs separately.

Release targets:

- retrieval recall at the configured context limit: at least 90%
- supported personal claims: at least 98%
- unknown-answer precision and recall: at least 90%
- speaker attribution after human review: 100% in the reviewed gold set

Do not tune retrieval weights, distance thresholds, routing phrases, or models
without saving a before-and-after report from the same reviewed case set.
