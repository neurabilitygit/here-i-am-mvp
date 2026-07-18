# Operations

## Startup checks

1. Confirm `/Volumes/Personal/here-i-am` is mounted.
2. Confirm native Ollama responds at `http://127.0.0.1:11434/api/tags`.
3. Run `scripts/start.sh`, which creates a clean build snapshot under `/tmp` before Docker sees the source.
4. Check `/api/health` for application/storage liveness and `/api/ready` for Ollama readiness.
5. For local cloned voice, run `scripts/start_voice.sh` and check `http://127.0.0.1:8779/health`.

For the current Railway-backed OpenAI benchmark, recreate the Here-I-Am container with `OPENAI_API_KEY` loaded in process memory from the linked Rising Senior Railway service. Do not copy the key into Compose, preferences, logs, or source control. Here I Am defaults to the lower-cost `gpt-5.4-mini`; the Railway service's own model selection is not changed.

## Production answer-engine controls

The production UI exposes two explicit choices under **Settings → Talk answer engine**:

- **Best answer — OpenAI GPT** uses the configured `OPENAI_MODEL` only for final Talk composition.
- **Private answer — Local Gemma** uses `OLLAMA_CHAT_MODEL` and keeps generation on this Mac.

The selected provider is persisted atomically in `/data/appdata/preferences.json`. A change is rejected before persistence when the destination provider is not usable: Local Gemma requires a reachable Ollama service and an installed chat model; OpenAI requires a production credential and a model in `ALLOWED_OPENAI_MODELS`. There is no automatic fallback in either direction. The settings response and `/api/providers/status` never expose credentials.

Production defaults disable browser entry of API keys with `ALLOW_RUNTIME_CLOUD_KEY=false`. Supply the key through `OPENAI_API_KEY`, or preferably mount a root-readable secret and set `OPENAI_API_KEY_FILE` to its container path. Browser-entered session keys are intended only for controlled development and require `ALLOW_RUNTIME_CLOUD_KEY=true`.

`/api/health` is the container liveness check. `/api/ready` is the deployment readiness gate and requires:

1. the data volume;
2. Ollama and the local `embeddinggemma` model, regardless of answer provider;
3. the currently selected answer provider.

Long local generations emit a server-sent-event heartbeat every 15 seconds. Upstream errors are logged locally while the browser receives a safe, actionable message without response bodies, credentials, or provider internals.

## Non-destructive controls

- Transcript updates create a prior revision and make derived analysis stale.
- Session archive requires `confirm=true` and moves, rather than deletes, data.
- Vector reindex requires `confirm=true`, writes only the migration collection, and does not activate it.
- Structured backups copy transcripts, metadata, chunks, state, and voice profile with SHA-256 checksums. They intentionally exclude audio and model weights; those require a separate volume-level backup policy.
- Voice preparation requires explicit rights confirmation and creates only `appdata/voice/voice_reference.wav` plus its short reference transcript and consent status.
- Voice revocation disables synthesis and may delete derived references without touching session audio.
- Cloud generation never activates as an automatic fallback.
- Selecting OpenAI changes only Talk response generation. Retrieval still uses the existing local `embeddinggemma` index, and TTS still uses the local voice bridge.
- New recordings remain in the memory queue until the user explicitly confirms **Prepare all memories**. The warning states that Here I Am is unavailable for the duration. The batch runs serially, uses local `gemma4:e4b` for metadata and local `embeddinggemma` for vectors, and unloads both when complete. `/api/memory-batch/status` reports the queue, active job, models, and the hard-coded `openai_embedding_enabled: false` boundary.

## Performance profile

The current local Talk model is `gemma4:e4b` with Ollama thinking explicitly disabled for interactive generation. Without that setting, the model can spend the entire output budget on hidden reasoning and return no visible answer. Quality-oriented retrieval uses 12 vector candidates, lexical reranking, 4 seed chunks, and neighboring-chunk expansion up to 6 context chunks.

The Talk settings provide Local Gemma and OpenAI GPT choices, plus a side-by-side comparison action. The comparison reuses one retrieval result and one prompt for both providers. Measure complete-answer time and inspect answer text and cited memories; it intentionally does not benchmark embeddings or voice generation.

Local cloned voice uses the Apple-native MLX Qwen3-TTS runtime. Its sentence foundry creates natural 15–30-word units, sends groups of up to four through MLX shared-reference `batch_generate`, applies text-length-aware token ceilings, and stitches the results with short pauses into one complete WAV. Safari never plays partial chunks. The reference waveform and MLX reference encodings are reused, while a persistent cache keyed by answer, voice reference, model, and speed makes repeated playback immediate. A 110-second watchdog bounds synthesis, request IDs support exact cancellation, and an abandoned HTTP request cancels its native job. The optional “Prepare voice while I read” setting starts rendering when the written answer arrives. The dog-and-ball scene remains active until the full WAV is ready.

Before local synthesis, the app unloads Gemma only when it is resident, leaving `embeddinggemma` untouched; the next local Talk request reloads Gemma normally. The bridge rejects overlapping synthesis with HTTP 409, while the browser waits and retries rather than presenting a false terminal failure. A controlled four-segment benchmark on this Mac produced 35.04 seconds of audio in 50.56 seconds with the BF16 model. The 4-bit model produced 38.56 seconds in 179.51 seconds, so BF16 remains the default because its wall-clock generation was about 3.55 times faster (and its elapsed time per generated audio second was about 3.23 times better).

## Recovery

- Interrupted jobs are reported in job history and may be retried.
- Run reconciliation before and after maintenance.
- Restore authoritative files first; rebuild metadata/chunks/index afterward.
- Never copy a Chroma directory while it is being written. Prefer a stopped-app volume snapshot or rebuild from portable artifacts.

## Deployment gate

Before replacing the existing container: run the test target, launch an isolated container with a synthetic empty data volume on another port, verify the UI and API, create a volume snapshot, and only then schedule a controlled cutover. Do not combine collection activation with the application rollout.

For a controlled cutover:

1. Record the current value returned by `/api/providers/status`.
2. Verify `OPENAI_MODEL` is present in `ALLOWED_OPENAI_MODELS` and keep `ALLOW_RUNTIME_CLOUD_KEY=false`.
3. Run the test image and synthetic-volume smoke test.
4. Create a stopped-app snapshot of `/Volumes/Personal/here-i-am`.
5. Rebuild through `scripts/start.sh`; do not build directly from AppleDouble-contaminated external-drive files.
6. Require HTTP 200 from both `/api/health` and `/api/ready` before opening Safari.
7. Switch once to each provider in Settings and confirm `/api/providers/status` reports the same active provider and `active_ready=true`.
8. Confirm the memory-batch endpoint still reports `openai_embedding_enabled: false`.
