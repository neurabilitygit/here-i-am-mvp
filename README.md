# Here I Am MVP

A local autobiography system built for a Mac with native Ollama and a Dockerized web application.

## Architecture

- **Native on macOS**: Ollama runtime and Gemma model
- **Native on macOS**: tiny Ollama control bridge so the browser buttons can start and stop Ollama
- **Docker container**: web UI, API, recording upload conversion, transcription, transcript analysis, Chroma persistence, and RAG chat
- **External drive**: all project data under `/Volumes/Personal/here-i-am`

## What the MVP does

1. **Local LLM Control**
   - Start Ollama
   - Stop Ollama
   - Refresh status

2. **Learning Mode**
   - Browser microphone recording
   - Record, pause, resume, and stop buttons work
   - Final audio is uploaded and converted to `recording.flac`
   - Each recording creates a new timestamped session folder

3. **Transcribing Mode**
   - Finds new recordings without transcripts
   - Runs Whisper locally in the app container
   - Writes `transcript.md`
   - Shows progress and current filename

4. **Analysis Mode**
   - Finds transcripts that have not yet been analyzed
   - Uses Gemma through Ollama to create `metadata.json`
   - Chunks transcript text and stores it in Chroma
   - Writes `chunks.jsonl`
   - Shows progress and current filename

5. **Here I Am**
   - Uses Chroma retrieval
   - Sends retrieved context to Gemma through Ollama
   - Returns a synthesized answer without quoting source passages

## Required external-drive folders

The container expects this host path to exist:

```text
/Volumes/Personal/here-i-am/
```

Recommended structure:

```text
/Volumes/Personal/here-i-am/
  library/sessions/
  appdata/chroma/
  appdata/logs/
  appdata/tmp/
  models/ollama/
  run/
```

## One-time native setup on the Mac

### 1. Keep Ollama models on Personal

```bash
launchctl setenv OLLAMA_MODELS /Volumes/Personal/here-i-am/models/ollama
```

Then restart Ollama if it is already running.

### 2. Pull models natively

```bash
ollama pull gemma4:e4b
ollama pull embeddinggemma
```

### 3. Run the Ollama control bridge on the Mac

Install the small dependencies once:

```bash
python3 -m pip install fastapi uvicorn requests
```

Start the bridge:

```bash
python3 -m uvicorn scripts.ollama_control_bridge:app --host 0.0.0.0 --port 8778 --app-dir .
```

Keep that process running. It gives the browser buttons a safe way to start and stop native Ollama.

## Start the containerized app

From the project root:

```bash
docker compose up --build
```

Open:

```text
http://localhost:8787
```

## Session folder contract

Each recording creates a folder like:

```text
/Volumes/Personal/here-i-am/library/sessions/2026-04-09_14-03-10_childhood-memories/
  recording.flac
  transcript.md
  metadata.json
  chunks.jsonl
  processing_state.json
```

## Notes

- The browser records compressed audio first, then the backend converts it to FLAC on stop.
- This keeps the browser flow simple while still storing archival FLAC.
- The MVP assumes **single-speaker recordings only**.
- There is **no manual transcript editor** in this version.
- The analysis and transcription jobs are idempotent. They skip work that already has output files.

## Best-practice simplifications used here

- One main app container instead of multiple internal services
- Native Ollama, because it runs more cleanly on Apple Silicon outside Docker
- No SQL database
- Chroma as the only retrieval store
- Filesystem as the durable source of truth

## Files included

- `Dockerfile`
- `docker-compose.yml`
- `app/main.py`
- `app/config.py`
- `app/templates/index.html`
- `app/static/app.js`
- `app/static/styles.css`
- `app/services/*`
- `scripts/ollama_control_bridge.py`

## Likely first adjustments after MVP

- Increase Whisper model size if transcript quality is not good enough
- Add explicit topic filters in chat
- Add a session browser
- Add transcript review and correction
- Add export and backup commands
