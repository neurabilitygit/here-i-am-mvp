# Architecture

## Runtime boundary

```text
Browser :8787
  -> FastAPI + static UI (Docker)
     -> session filesystem (authoritative)
     -> durable job JSON + advisory locks
     -> faster-whisper (CPU transcription)
     -> OpenAI diarized transcription (explicit two-person conversation batches)
     -> Chroma (derived vector index)
     -> Ollama :11434 on macOS (generation + embeddings)
     -> MLX Qwen3-TTS batch-WAV bridge :8779 on macOS (optional local cloned voice)
     -> OpenAI / ElevenLabs APIs (optional, explicit cloud mode)
```

The root `Dockerfile`, `docker-compose.yml`, and `app/` define the active runtime. The duplicate `backend/`, `frontend/`, `worker/`, and nested `app/app/` trees are dormant prototypes. They remain in place for historical comparison but must not receive new product changes.

## Data pipeline

1. The browser records or uploads compressed audio and places it in the local memory queue. No analysis or embedding starts automatically.
2. FastAPI streams it to a unique session and enforces a size limit.
3. The original upload is retained as `recording.source`; FFmpeg creates a mono 16 kHz FLAC analysis copy.
4. After explicit warning and confirmation, solo recordings run local Whisper. Conversation recordings create a compact Opus analysis copy and use OpenAI diarized transcription with any available speaker voice references.
5. Unknown conversation voices pause at a mandatory name-and-role review. Exactly one voice is the memory subject. The pipeline writes labeled turns plus subject-only memory units; interviewer speech remains retrieval context and cannot become autobiographical evidence.
6. The same batch uses the strongest configured local Gemma generation model to create validated metadata, semantic word-bounded chunks, portable JSONL, and voice-profile evidence.
7. The purpose-built local `embeddinggemma` model creates vectors in the active Chroma collection. Both Gemma models are unloaded when the batch ends, including on failure. OpenAI has no embedding path.
8. Chat retrieves a broad vector candidate set, reranks it by lexical overlap with the question, and expands the strongest matches with neighboring chunks from the same recording. Query vectors also use local `embeddinggemma`, which is unloaded after the query.
9. Questions route to `PERSONAL`, `GENERAL`, or `HYBRID`. Personal context is tagged as untrusted evidence, bounded by chunk and character limits, and source session IDs are returned separately.
10. A provider layer streams generation tokens from local Ollama or an explicitly selected OpenAI model. The comparison endpoint prepares retrieval and the speaker prompt once, then runs both providers in parallel against that identical evidence so the benchmark measures answer generation rather than embedding or TTS differences.
11. The speaker fingerprint measures transcript vocabulary/rhythm and original-audio pace without modifying source recordings.
12. Consented TTS uses a derived normalized reference; the portrait reacts to returned audio energy in the browser.

## Reliability boundaries

- Session artifacts use temporary-file, fsync, and atomic replace semantics.
- Per-session advisory locks prevent concurrent transcript/analysis mutation.
- A single-worker durable job manager plus cross-process advisory locks prevents conflicting jobs of the same mode.
- The local MLX voice bridge accepts only one synthesis at a time. A sentence-foundry stage creates 15–30-word speech units; groups of up to four use MLX shared-reference batch generation with per-sequence text-length limits. The bridge reuses reference conditioning, stitches the units into one WAV, persists answer/voice/speed cache entries, and returns only the completed file to Safari. Request IDs, disconnect-aware cancellation, segment progress, busy age, a 110-second no-progress watchdog, and a 120-second per-attempt ceiling prevent abandoned work from becoming an invisible stale lock. Completed segment files remain resumable after a timed-out attempt.
- Transcript edits preserve immutable prior revisions and immediately make the prior vector version ineligible for retrieval.
- Archive moves a session into `library/archive`. Its Chroma records are permanently retained but cannot be selected because the session is absent from the active manifest.
- Chroma writes are append-only. Versioned vectors and artifacts are staged first; `active_content_version` is the final activation step.
- Conversation sessions cannot enter analysis or Chroma until every detected voice is assigned and exactly one subject is chosen. Reprocessing reuses durable diarization and turn artifacts.
- Reconciliation checks filesystem state, artifact versions, and activated Chroma coverage without repairing or deleting anything.

## Trust boundaries

The service is intended for localhost. Compose publishes only to `127.0.0.1`, trusted hosts and CORS are restricted, cross-origin mutations are rejected, uploads are bounded by encoded size and decoded duration, production API documentation is disabled, and the read-only container runs as a non-root user. Authentication and encryption at rest remain requirements before any network exposure.

Cloud is explicit and purpose-specific. Talk requests contain only the current question, selected context, speaker instructions, and a bounded derived speaking-style profile. A conversation batch sends its compressed audio analysis copy to the configured diarization provider. Avatar generation sends the consented face photo and an art-style reference. API keys are sourced from environment variables, a protected file, or process memory and never persisted in experience preferences. Embeddings always remain local.
