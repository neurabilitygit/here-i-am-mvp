# Here I Am

A local-first autobiography system for recording, transcribing, structuring, retrieving, and exploring a personal archive through an animated “Living Portrait.” Ollama and optional cloned-voice synthesis run natively on macOS; the FastAPI application runs in Docker; durable data remains under `/Volumes/Personal/here-i-am`.

## Current architecture

- `app/` is the only active application implementation.
- `backend/`, `frontend/`, `worker/`, and `app/app/` are retained legacy prototypes and are not part of the root Docker build.
- Files under `library/sessions/` are the durable source of truth.
- Chroma is append-only: revisions and archives preserve every historical vector. Retrieval uses the active filesystem version manifest so only the current, non-archived version can answer.
- Background-job state is persisted as JSON and interrupted work becomes safely retryable after restart.

See [Architecture](docs/ARCHITECTURE.md), [Data contracts](docs/DATA_CONTRACTS.md), [Operations](docs/OPERATIONS.md), and [migration notes](docs/REFACTOR_MIGRATION.md).

## Safe local workflow

The external drive produces AppleDouble files that Docker cannot always read. Build from a clean local snapshot:

```bash
./scripts/start.sh
```

Then open `http://localhost:8787`. This mounts the existing data directory; it does not migrate or delete it.

For tests, build without mounting personal data:

```bash
rsync -a --delete --exclude='.git' --exclude='._*' --exclude='venv' ./ /tmp/here-i-am-test/
xattr -rc /tmp/here-i-am-test
docker build --target test -t here-i-am-test /tmp/here-i-am-test
docker run --rm here-i-am-test
```

## Native dependencies

Ollama models are expected at `/Volumes/Personal/here-i-am/models/ollama`:

```bash
launchctl setenv OLLAMA_MODELS /Volumes/Personal/here-i-am/models/ollama
ollama pull gemma4:e4b
ollama pull embeddinggemma
ollama serve
```

The optional control bridge should only listen locally:

```bash
python3 -m uvicorn scripts.ollama_control_bridge:app --host 127.0.0.1 --port 8778 --app-dir .
```

## Product surfaces

- Three stable visual activities: Talk, Remember, and Memories
- Customizable local SVG portrait with listening, thinking, and audio-reactive speaking states
- One-touch recording with an animated waveform and a visible local-processing queue
- Explicit batch preparation using local `gemma4:e4b` analysis plus `embeddinggemma`; OpenAI is never used for embeddings
- Two-person conversation capture with cloud speaker diarization, reusable voice references, an explicit name-and-role review gate, and subject-only autobiographical evidence
- A persistent People gallery with one voice profile and avatar per speaker; users may upload an illustration or consent to turn a face photo into a matching non-photorealistic avatar
- Visual memory gallery with transcript review and revision history
- Read-only reconciliation report
- Per-session ZIP export and full rebuildable checksum backups, including original recordings and an append-only Chroma export
- Streamed personal/general/hybrid chat with source memories and answer feedback
- Quantitative vocabulary, rhythm, phrase, and audio-pace fingerprinting
- Optional OpenAI-compatible cloud generation with explicit disclosure and session-only key handling
- Production-validated answer-engine selection with no silent fallback; embeddings remain local in every mode
- Consented local Qwen3-TTS or ElevenLabs cloned-voice playback
- Side-by-side v2 vector reindex plan and explicit-confirmation job

The active collection is never switched automatically. Validate `here_i_am_chunks_v2` before changing `CHROMA_COLLECTION` in a future, separately approved deployment.

## Two-person conversations

Choose **A conversation** before recording or importing audio. The explicit memory batch sends a compressed analysis copy to `gpt-4o-transcribe-diarize` to separate voices and match up to four stored 2–10 second voice references. Unknown voices stop at a visual review gate where the user names each person and chooses exactly one memory subject. Interviewer questions are retained as retrieval context, but only the subject's words are analyzed as autobiographical evidence or embedded. Metadata and vectors continue to use local Gemma and local `embeddinggemma`; Chroma remains append-only.

Each confirmed speaker receives a durable profile under `appdata/speakers`. A speaker can use an uploaded illustrated avatar directly. With explicit image-rights confirmation, a face photo and the existing Here I Am art reference can be sent to `gpt-image-2` to produce a non-photorealistic portrait. Originals and all generated versions remain in the rebuildable backup set.

## Optional local cloned voice

The main app runs without voice synthesis. To enable private, reference-conditioned speech on Apple Silicon, install and start the separate native bridge:

```bash
./scripts/start_voice.sh
```

The first run creates an isolated native environment and downloads the configured Qwen3-TTS model. The voice bridge divides an answer into natural speech segments, generates up to four segments together against one cached reference, and stitches them into a single WAV for Safari. Completed answers are cached, active work is cancellable, and a 110-second watchdog prevents an abandoned request from holding the voice indefinitely. In Settings, the recorded speaker must confirm voice rights and select a reference recording before synthesis is enabled. “Prepare voice while I read” can render the WAV in the background as soon as a written answer appears. Original recordings are never edited.

See [Immersive product plan](docs/IMMERSIVE_PRODUCT_PLAN.md) and [voice/cloud consent](docs/VOICE_AND_CLOUD_CONSENT.md).

## Mobile access

Here I Am now requires logging in with a shared passphrase (`./scripts/set_passphrase.py` to set it) and can be reached from a phone over a private Tailscale mesh network — never a LAN binding or a public tunnel. See [Operations: Remote access via Tailscale](docs/OPERATIONS.md#remote-access-via-tailscale) for setup.
