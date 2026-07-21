# Data contracts

## Session directory

Each directory in `library/sessions/<session_id>/` may contain:

| Artifact | Role | Authority |
|---|---|---|
| `recording.source` | Byte-for-byte uploaded or browser-recorded audio | Source |
| `recording.flac` | Normalized mono analysis audio | Derived/rebuild input |
| `transcript.md` | Human-reviewable transcript | Source |
| `diarization.json` | Provider/model audit plus detected turns | Derived/rebuild input |
| `transcript.turns.json` | Time-bounded voice-labeled conversation turns | Source for conversation review |
| `speaker_assignments.json` | User-confirmed cluster-to-person and role map | Source |
| `memory_units.jsonl` | Subject evidence with interviewer retrieval context separated | Source for conversation indexing |
| `transcript.revisions/*` | Prior transcript versions and reasons | Audit history |
| `metadata.json` | Validated structured analysis | Derived |
| `chunks.jsonl` | Portable semantic chunks and metadata | Derived/rebuild input |
| `processing_state.json` | Versioned pipeline state | Operational |
| `versions/<content_version>/metadata.json` | Immutable metadata for an indexed version | Derived history |
| `versions/<content_version>/chunks.jsonl` | Immutable portable chunks for an indexed version | Derived history |

Session identifiers contain a timestamp, optional title slug, and random suffix. API path validation forbids nested paths.

## Processing state v4

Boolean artifact flags are paired with explicit status fields, `updated_at`, and `active_content_version`. The active version is changed only after its versioned artifacts and Chroma records are durable. A revised transcript is ineligible for retrieval until its replacement version is activated.

Conversation sessions add `recording_mode`, `speaker_processing_status`, `speaker_review_status`, `speaker_count`, and `subject_speaker_id`. Analysis requires `speaker_review_status=complete` and a durable `memory_units.jsonl`.

## Speaker registry

`appdata/speakers/registry.json` maps stable speaker IDs to display names, default roles, a derived 2–10 second WAV reference, source photos, avatar versions, and the active avatar. Speaker media lives under `appdata/speakers/<speaker_id>/`. New versions are added; changing an active avatar does not remove prior files.

## Metadata v2

`metadata.json` is validated against `TranscriptMetadata`: identity/title/summary, topics, people, places, time period, emotional tone, content type, notable events, a structured style profile, and style exemplars. Long transcripts are summarized in stages so the end of the input is not silently discarded.

## Vector collections

- Active: `here_i_am_chunks`
- Migration candidate: `here_i_am_chunks_v2`

Legacy chunk IDs remain readable as `<session_id>::chunk::<index>`. New IDs are `<session_id>::version::<content_version>::chunk::<index>`. Chroma is append-only: the application never deletes vectors. Superseded and archived records remain preserved, while retrieval accepts only the version named in the active filesystem manifest. Reindexing adds missing versioned records to the target collection and never switches collections automatically.

## Durable jobs

Jobs are stored under `appdata/jobs/<uuid>.json` with mode, status, progress, timestamps, result, and completion flag. Queued/running jobs found after a process restart become `interrupted` and completed, making an explicit retry safe.
