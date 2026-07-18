# Data contracts

## Session directory

Each directory in `library/sessions/<session_id>/` may contain:

| Artifact | Role | Authority |
|---|---|---|
| `recording.flac` | Archival mono audio | Source |
| `transcript.md` | Human-reviewable transcript | Source |
| `transcript.revisions/*` | Prior transcript versions and reasons | Audit history |
| `metadata.json` | Validated structured analysis | Derived |
| `chunks.jsonl` | Portable semantic chunks and metadata | Derived/rebuild input |
| `processing_state.json` | Versioned pipeline state | Operational |

Session identifiers contain a timestamp, optional title slug, and random suffix. API path validation forbids nested paths.

## Processing state v2

Boolean artifact flags (`recorded`, `transcribed`, `analyzed`, `embedded`) are paired with explicit status fields and `updated_at`. The filesystem remains authoritative: `/api/reconciliation` compares declared state to artifacts and never silently repairs discrepancies.

## Metadata v2

`metadata.json` is validated against `TranscriptMetadata`: identity/title/summary, topics, people, places, time period, emotional tone, content type, notable events, a structured style profile, and style exemplars. Long transcripts are summarized in stages so the end of the input is not silently discarded.

## Vector collections

- Active: `here_i_am_chunks`
- Migration candidate: `here_i_am_chunks_v2`

Chunk IDs are deterministic: `<session_id>::chunk::<index>`. Chroma is disposable derived state; transcript and metadata artifacts are retained. Reindexing deletes and replaces only matching session records in the target collection. It never switches or deletes the active collection.

## Durable jobs

Jobs are stored under `appdata/jobs/<uuid>.json` with mode, status, progress, timestamps, result, and completion flag. Queued/running jobs found after a process restart become `interrupted` and completed, making an explicit retry safe.
