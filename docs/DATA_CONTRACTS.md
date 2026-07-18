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
| `versions/<content_version>/metadata.json` | Immutable metadata for an indexed version | Derived history |
| `versions/<content_version>/chunks.jsonl` | Immutable portable chunks for an indexed version | Derived history |

Session identifiers contain a timestamp, optional title slug, and random suffix. API path validation forbids nested paths.

## Processing state v3

Boolean artifact flags are paired with explicit status fields, `updated_at`, and `active_content_version`. The active version is changed only after its versioned artifacts and Chroma records are durable. A revised transcript is ineligible for retrieval until its replacement version is activated.

## Metadata v2

`metadata.json` is validated against `TranscriptMetadata`: identity/title/summary, topics, people, places, time period, emotional tone, content type, notable events, a structured style profile, and style exemplars. Long transcripts are summarized in stages so the end of the input is not silently discarded.

## Vector collections

- Active: `here_i_am_chunks`
- Migration candidate: `here_i_am_chunks_v2`

Legacy chunk IDs remain readable as `<session_id>::chunk::<index>`. New IDs are `<session_id>::version::<content_version>::chunk::<index>`. Chroma is append-only: the application never deletes vectors. Superseded and archived records remain preserved, while retrieval accepts only the version named in the active filesystem manifest. Reindexing adds missing versioned records to the target collection and never switches collections automatically.

## Durable jobs

Jobs are stored under `appdata/jobs/<uuid>.json` with mode, status, progress, timestamps, result, and completion flag. Queued/running jobs found after a process restart become `interrupted` and completed, making an explicit retry safe.
