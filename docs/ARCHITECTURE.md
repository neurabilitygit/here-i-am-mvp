# Architecture

## Runtime boundary

```text
Browser :8787
  -> FastAPI + static UI (Docker)
     -> session filesystem (authoritative)
     -> durable job JSON + advisory locks
     -> faster-whisper (CPU transcription)
     -> Chroma (derived vector index)
     -> Ollama :11434 on macOS (generation + embeddings)
     -> MLX Qwen3-TTS batch-WAV bridge :8779 on macOS (optional local cloned voice)
     -> OpenAI / ElevenLabs APIs (optional, explicit cloud mode)
```

The root `Dockerfile`, `docker-compose.yml`, and `app/` define the active runtime. The duplicate `backend/`, `frontend/`, `worker/`, and nested `app/app/` trees are dormant prototypes. They remain in place for historical comparison but must not receive new product changes.

## Data pipeline

1. The browser records or uploads compressed audio and places it in the local memory queue. No analysis or embedding starts automatically.
2. FastAPI streams it to a unique session and enforces a size limit.
3. FFmpeg converts the upload to mono 16 kHz FLAC.
4. After explicit warning and confirmation, one serialized durable batch runs local Whisper and atomically writes `transcript.md`.
5. The same batch uses the strongest configured local Gemma generation model to create validated metadata, semantic word-bounded chunks, portable JSONL, and voice-profile evidence.
6. The purpose-built local `embeddinggemma` model creates vectors in the active Chroma collection. Both Gemma models are unloaded when the batch ends, including on failure. OpenAI has no embedding path.
7. Chat retrieves a broad vector candidate set, reranks it by lexical overlap with the question, and expands the strongest matches with neighboring chunks from the same recording. Query vectors also use local `embeddinggemma`, which is unloaded after the query.
8. Questions route to `PERSONAL`, `GENERAL`, or `HYBRID`. Personal context is tagged as untrusted evidence, bounded by chunk and character limits, and source session IDs are returned separately.
9. A provider layer streams generation tokens from local Ollama or an explicitly selected OpenAI model. The comparison endpoint prepares retrieval and the speaker prompt once, then runs both providers in parallel against that identical evidence so the benchmark measures answer generation rather than embedding or TTS differences.
10. The speaker fingerprint measures transcript vocabulary/rhythm and original-audio pace without modifying source recordings.
11. Consented TTS uses a derived normalized reference; the portrait reacts to returned audio energy in the browser.

## Reliability boundaries

- Session artifacts use temporary-file, fsync, and atomic replace semantics.
- Per-session advisory locks prevent concurrent transcript/analysis mutation.
- A single-worker durable job manager prevents conflicting jobs of the same mode.
- The local MLX voice bridge accepts only one synthesis at a time. A sentence-foundry stage creates 15–30-word speech units; groups of up to four use MLX shared-reference batch generation with per-sequence text-length limits. The bridge reuses reference conditioning, stitches the units into one WAV, persists answer/voice/speed cache entries, and returns only the completed file to Safari. Request IDs, disconnect-aware cancellation, segment progress, busy age, and a 110-second watchdog prevent abandoned work from becoming an invisible stale lock.
- Transcript edits preserve immutable prior revisions and mark analysis/index state stale.
- Archive moves a session into `library/archive`; no delete endpoint exists.
- Reconciliation reports mismatches without repairing them.

## Trust boundaries

The service is intended for localhost. Compose publishes only to `127.0.0.1`, trusted hosts and CORS are restricted, uploads are bounded, path traversal is rejected, and browser responses carry defensive headers. Authentication and encryption at rest remain future requirements before any network exposure.

Cloud is explicit and provider-selectable. A cloud request contains only the current question, selected context, and speaker instructions. API keys are sourced from environment variables or process memory and never persisted in experience preferences. Embeddings, recordings, transcription, and voice synthesis remain local when OpenAI is selected for Talk generation.
